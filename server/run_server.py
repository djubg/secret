import uvicorn

from app.core.settings import get_settings


def main():
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)


if __name__ == "__main__":
    main()
