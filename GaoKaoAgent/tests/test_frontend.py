from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from fastapi.testclient import TestClient

from app.main import app


class LocalAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        value = attributes.get("src") if tag == "script" else attributes.get("href") if tag == "link" else None
        if value and not urlparse(value).scheme:
            self.paths.append(value)


def test_frontend_pages_and_local_assets():
    pages = ["index.html", *(
        f"pages/{name}.html" for name in
        ("student", "universities", "recommendation", "agents", "knowledge", "models", "history")
    )]
    with TestClient(app) as client:
        assert client.get("/", follow_redirects=False).headers["location"] == "/static/index.html"
        for page in pages:
            path = f"/static/{page}"
            response = client.get(path)
            assert response.status_code == 200, path
            assert 'src=' in response.text
            assets = LocalAssets()
            assets.feed(response.text)
            assert assets.paths, path
            for asset in assets.paths:
                asset_path = urljoin(path, asset)
                assert client.get(asset_path).status_code == 200, asset_path
