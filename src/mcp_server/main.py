
from typing import Any
import sys
import os
from io import TextIOWrapper
import json
from pydantic import BaseModel, model_validator
from flask import Flask, request, Response
#from flask_sock import Sock

PORT = 8042
HOST = "0.0.0.0"

class McpTools(BaseModel):

    out_format: str
    in_format: str
    io_output: Any = sys.stdout
    io_error: Any = sys.stderr
        
    # TOOLS ---------------------------------------//
    
    @model_validator(mode="after")
    def check_write_path(self) -> "McpTools":
        if not isinstance(self.io_output, TextIOWrapper):
            raise ValueError(f"{self.io_output} not valid TextIOWrapper")
        if not isinstance(self.io_error, TextIOWrapper):
            raise ValueError(f"{self.io_error} not valid TextIOWrapper")
        return self

    def read_file(self, filepath, start_line, end_line):
        pass

    def edit_file(self, filepath, old_str, new_str):
        pass

    def list_files(self, directory, pattern):
        pass



    def search_code(self, pattern, file_pattern):
        pass

    def search_function_or_class_definition_in_code(self, name):
        pass

    def find_references(self, name, filepath, line):
        pass



    def run_tests(self):
        pass

    def get_patch(self):
        pass

    def run_command(self, command, workdir):
        pass


app = Flask(__name__)
tools = McpTools(out_format="http", in_format="http")


@app.get("/")
def get_exchange() -> Response:
    return Response("")


@app.post("/")
def post_exchange() -> Response:
    try:
        data = json.loads(request.data)
        print("data received:", data)
    except Exception as e:
        print(f"erro occured in data received {e}", file=tools.io_error)

    return Response("")


if __name__ == "__main__":
    try:
        app.run(host=HOST, port=PORT)
    except Exception as e:
        print(f"server crashed with error : {e}")
