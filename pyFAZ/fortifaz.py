#!/usr/bin/env python

from datetime import datetime
import time
import logging
import json
import requests
from requests.exceptions import ConnectionError as ReqConnError, ConnectTimeout as ReqConnTimeout

log = logging.getLogger("fortiAnalyzer")


class FAZBaseException(Exception):
    """Wrapper to catch the unexpected"""

    def __init__(self, msg=None, *args, **kwargs):
        if msg is None:
            msg = "An exception occurred within pyFAZ"
        super(FAZBaseException, self).__init__(msg, *args)


class FAZValidSessionException(FAZBaseException):
    """Raised when a call is made, but there is no valid login instance"""

    def __init__(self, method, params, *args, **kwargs):
        msg = "A call using the {method} method was requested to {url} on a FortiAnalyzer instance that had no " \
              "valid session or was not connected. Paramaters were:\n{params}". \
            format(method=method, url=params[0]["url"], params=params)
        super(FAZValidSessionException, self).__init__(msg, *args, **kwargs)


class FAZValueError(ValueError):
    """Catch value errors such as bad timeout values"""

    def __init__(self, *args):
        super(FAZValueError, self).__init__(*args)


class FAZResponseNotFormedCorrect(KeyError):
    """Used only if a response does not have a standard format as based on FAZ response guidelines"""

    def __init__(self, *args):
        super(FAZResponseNotFormedCorrect, self).__init__(*args)


class FAZConnectionError(ReqConnError):
    """Wrap requests Connection error so requests is not a dependency outside this module"""

    def __init__(self, *args, **kwargs):
        super(FAZConnectionError, self).__init__(*args, **kwargs)


class FAZConnectTimeout(ReqConnTimeout):
    """Wrap requests Connection timeout error so requests is not a dependency outside this module"""

    def __init__(self, *args, **kwargs):
        super(FAZConnectTimeout, self).__init__(*args, **kwargs)


class FAZRequestNotFormedCorrect(FAZBaseException):
    """Used only if a request does not have a standard format as based on FAZ request guidelines"""

    def __init__(self, msg=None, *args, **kwargs):
        super(FAZRequestNotFormedCorrect, self).__init__(msg=msg, *args, **kwargs)


class FortiAnalyzer(object):

    def __init__(self, host=None, user="", passwd="", debug=False, use_ssl=True, verify_ssl=False, timeout=300,
                 disable_request_warnings=False):
        super(FortiAnalyzer, self).__init__()
        self._debug = debug
        self._host = host
        self._user = user
        self._passwd = passwd
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._req_id = 0
        self._sid = None
        self._url = None
        self._socket = requests.session()
        if disable_request_warnings:
            requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, val):
        self._debug = val

    @property
    def req_id(self):
        return self._req_id

    @req_id.setter
    def req_id(self, val):
        self._req_id = val

    def _update_request_id(self, reqid=0):
        self.req_id = reqid if reqid != 0 else self.req_id + 1

    @property
    def sid(self):
        return self._sid

    @sid.setter
    def sid(self, val):
        self._sid = val

    @property
    def verify_ssl(self):
        return self._verify_ssl

    @verify_ssl.setter
    def verify_ssl(self, val):
        self._verify_ssl = val

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, val):
        self._timeout = val

    @property
    def sock(self):
        return self._socket

    @staticmethod
    def jprint(json_obj):
        try:
            return json.dumps(json_obj, indent=2, sort_keys=True)
        except TypeError as te:
            return json.dumps({"Type Information": te.message})

    def dprint(self, msg, s=None):
        if self.debug:
            print(msg)
            if s is not None:
                print(self.jprint(s) + "\n")
        pass

    def _set_sid(self, response):
        if self.sid is None and "session" in response:
            self.sid = response["session"]

    def _handle_response(self, response):
        self._set_sid(response)
        if type(response["result"]) is list:
            result = response["result"][0]
        else:
            result = response["result"]
        if "data" in result:
            return result["status"]["code"], result["data"]
        else:
            try:
                return result["status"]["code"], result
            except KeyError:
                return 0, result

    def _post_request(self, method, params, login=False, free_form=False, create_task=None):
        if self.sid is None and not login:
            raise FAZValidSessionException(method, params)
        self._update_request_id()
        headers = {"content-type": "application/json"}
        json_request = {}
        if create_task:
            json_request["create task"] = create_task
            json_request["method"] = method
            json_request["params"] = params
            json_request["session"] = self.sid
            json_request["id"] = self.req_id
        else:
            json_request["method"] = method
            json_request["params"] = params
            json_request["session"] = self.sid
            json_request["id"] = self.req_id
            json_request["jsonrpc"] = "2.0"
        self.dprint("REQUEST:", json_request)
        try:
            response = self.sock.post(self._url, data=json.dumps(json_request), headers=headers, verify=self.verify_ssl,
                                      timeout=self.timeout).json()
            self.dprint("RESPONSE:", response)
            if free_form:
                return 0, response
            else:
                return self._handle_response(response)
        except ReqConnError as err:
            self.dprint("Connection error: {err_type} {err}\n\n".format(err_type=type(err), err=err))
            raise FAZConnectionError(err)
        except ValueError as err:
            self.dprint("Value error: {err_type} {err}\n\n".format(err_type=type(err), err=err))
            raise FAZValueError(err)
        except KeyError as err:
            self.dprint("Key error in response: {err_type} {err}\n\n".format(err_type=type(err), err=err))
            raise FAZResponseNotFormedCorrect(err)
        except IndexError as err:
            self.dprint("Index error in response: {err_type} {err}\n\n".format(err_type=type(err), err=err))
            raise FAZResponseNotFormedCorrect(err)
        except Exception as err:
            self.dprint("Response parser error: {err_type} {err}".format(err_type=type(err), err=err))
            raise FAZBaseException(err)

    def track_task(self, task_id, sleep_time=5, retrieval_fail_gate=10, timeout=120):
        begin_task_time = datetime.now()
        start = time.time()
        self.dprint("Task begins at {time}".format(time=str(begin_task_time)))
        percent = 0
        code_fail = 0
        code = 1
        task_info = ""
        while percent != 100:
            code, task_info = self.get("/task/task/{taskid}".format(taskid=task_id))
            if code == 0:
                percent = int(task_info["percent"])
                num_done = int(task_info["num_done"])
                num_err = int(task_info["num_err"])
                num_lines = int(task_info["num_lines"])
                self.dprint("At timestamp {timestamp}:\nTask {taskid} is at {percent}% completion.\n{num_err} "
                            "tasks have returned an error.".format(timestamp=datetime.now(),
                                                                   taskid=str(task_id), percent=str(percent),
                                                                   num_done=str(num_done), num_lines=str(num_lines),
                                                                   num_err=str(num_err)), task_info)
            else:
                code_fail += 1
            if code_fail == retrieval_fail_gate:
                self.dprint("Task info retrieval failed over {fail_gate} times. Something has caused issues "
                            "with task {taskid}.".format(taskid=task_id, fail_gate=retrieval_fail_gate))
                return code, task_info
            if percent != 100:
                if time.time() - start >= timeout:
                    self.dprint("Task did not complete in efficient time. The timeout value was {}".format(timeout))
                    return 1, {"msg": "Task did not complete in efficient time. "
                                      "The timeout value was {}".format(timeout)}
                else:
                    time.sleep(sleep_time)
        end_task_time = datetime.now()
        task_info["total_task_time"] = str(end_task_time - begin_task_time)
        self.dprint("Task completion is at {time}".format(time=str(end_task_time)))
        self.dprint("Total time to complete is {time}".format(time=str(end_task_time - begin_task_time)))
        return code, task_info

    def login(self):
        self._url = "{proto}://{host}/jsonrpc".format(proto="https" if self._use_ssl else "http", host=self._host)
        self.execute("sys/login/user", login=True, passwd=self._passwd, user=self._user, )
        if self.__str__() == "FortiAnalyzer instance connnected to {host}.".format(host=self._host):
            return 0, {"status": {"message": "OK", "code": 0}, "url": "sys/login/user"}
        else:
            return -1, {"status": {"message": self, "code": -1}, "url": "sys/login/user"}

    def logout(self):
        if self.sid is not None:
            ret_code, response = self.execute("sys/logout")
            self.sid = None
            return ret_code, response

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    @staticmethod
    def common_datagram_params(method_type, url, *args, **kwargs):
        params = [{"url": url, "apiver": 3}]

        urls_that_use_data = [
            "sys/",
            "dvmdb/adom",
        ]
        use_data_key = False
        for u in urls_that_use_data:
            if u in url:
                use_data_key = True

        if args:
            for arg in args:
                params[0].update(arg)
        if kwargs:
            keylist = list(kwargs)
            for k in keylist:
                kwargs[k.replace("___", " ").replace("__", "-")] = kwargs.pop(k)
            if method_type == "get" or method_type == "clone":
                params[0].update(kwargs)
            else:

                if kwargs.get("data", False):
                    if use_data_key:
                        params[0]["data"] = kwargs["data"]
                    else:
                        params[0].update(kwargs["data"])
                else:
                    if use_data_key:
                        params[0]["data"] = kwargs
                    else:

                        params[0].update(kwargs)
        return params

    def get(self, url, *args, **kwargs):
        return self._post_request("get", self.common_datagram_params("get", url, *args, **kwargs))

    def add(self, url, *args, **kwargs):
        return self._post_request("add", self.common_datagram_params("add", url, *args, **kwargs))

    def update(self, url, *args, **kwargs):
        return self._post_request("update", self.common_datagram_params("update", url, *args, **kwargs))

    def set(self, url, *args, **kwargs):
        return self._post_request("set", self.common_datagram_params("set", url, *args, **kwargs))

    def delete(self, url, *args, **kwargs):
        return self._post_request("delete", self.common_datagram_params("delete", url, *args, **kwargs))

    def replace(self, url, *args, **kwargs):
        return self._post_request("replace", self.common_datagram_params("replace", url, *args, **kwargs))

    def clone(self, url, *args, **kwargs):
        return self._post_request("clone", self.common_datagram_params("clone", url, *args, **kwargs))

    def execute(self, url, login=False, *args, **kwargs):
        return self._post_request("exec", self.common_datagram_params("execute", url, *args, **kwargs), login)

    def move(self, url, *args, **kwargs):
        return self._post_request("move", self.common_datagram_params("move", url, *args, **kwargs))

    def unset(self, url, *args, **kwargs):
        return self._post_request("unset", self.common_datagram_params("unset", url, *args, **kwargs))

    def free_form(self, method, create_task=None, **kwargs):
        if kwargs:
            if kwargs.get("data", False):
                return self._post_request(method, kwargs["data"], free_form=True, create_task=create_task)
            else:
                raise FAZRequestNotFormedCorrect("Free Form Request was not formed correctly. A data key is required")
        else:
            raise FAZRequestNotFormedCorrect("Free Form Request was not formed correctly. A dictionary object with a "
                                             "data key is required")

    def __str__(self):
        if self.sid is not None:
            return "FortiAnalyzer instance connnected to {host}.".format(host=self._host)
        return "FortiAnalyzer object with no valid connection to a FortiAnalyzer appliance."

    def __repr__(self):
        if self.sid is not None:
            return "{classname}(host={host}, pwd omitted, debug={debug}, use_ssl={use_ssl}, " \
                   "verify_ssl={verify_ssl}, timeout={timeout})".format(classname=self.__class__.__name__,
                                                                        host=self._host, debug=self._debug,
                                                                        use_ssl=self._use_ssl, timeout=self._timeout,
                                                                        verify_ssl=self._verify_ssl)
        return "FortiAnalyzer object with no valid connection to a FortiAnalyzer appliance."
