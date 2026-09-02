
import httpx



if __name__ == "__main__":


    data= "{}"
    r2 = httpx.post("http://127.0.0.1:8042/", data=data)
    print(r2)
