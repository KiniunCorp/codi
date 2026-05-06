from fastapi import FastAPI

app = FastAPI(title="CODI FastAPI Demo")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello from the CODI FastAPI demo!"}
