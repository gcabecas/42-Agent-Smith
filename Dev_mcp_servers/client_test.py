
import httpx
import json


if __name__ == "__main__":


    data= """
    {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "read_file",
        "arguments": {
            "filepath": "."
        }
      }
    }
    """
    r2 = httpx.post("http://127.0.0.1:8042/", data=data)
    print(r2)
    print(r2.text)
