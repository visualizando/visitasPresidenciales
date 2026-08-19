import httpx

from pipeline import discovery


def client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_discovers_index_json(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("index.json")
        return httpx.Response(
            200,
            json={
                "files": [
                    {"path": "casa-rosada/2023/01/datos.pdf", "size": 123, "sha256": "a" * 64}
                ]
            },
        )

    monkeypatch.setattr(discovery, "_client", lambda: client_for(handler))
    files = discovery.discover("https://example.org/accesos/")
    assert len(files) == 1
    assert files[0].location == "casa-rosada"
    assert files[0].month == 1
    assert files[0].sha256 == "a" * 64


def test_discovers_apache_style_directories(monkeypatch) -> None:
    pages = {
        "/accesos/index.json": (404, ""),
        "/accesos/": (200, '<a href="casa-rosada/">Casa Rosada</a>'),
        "/accesos/casa-rosada/": (200, '<a href="2023/">2023</a>'),
        "/accesos/casa-rosada/2023/": (200, '<a href="01/">01</a>'),
        "/accesos/casa-rosada/2023/01/": (200, '<a href="enero.pdf">enero.pdf</a>'),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-length": "99", "etag": '"abc"'})
        status, text = pages[request.url.path]
        return httpx.Response(status, text=text)

    monkeypatch.setattr(discovery, "_client", lambda: client_for(handler))
    files = discovery.discover("https://example.org/accesos/")
    assert [(item.path, item.size, item.etag) for item in files] == [
        ("casa-rosada/2023/01/enero.pdf", 99, '"abc"')
    ]


def test_rejects_unstructured_month(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"files": [{"path": "olivos/2023/datos.pdf"}]})

    monkeypatch.setattr(discovery, "_client", lambda: client_for(handler))
    try:
        discovery.discover("https://example.org/")
    except discovery.DiscoveryError as error:
        assert "mes" in str(error)
    else:
        raise AssertionError("Se esperaba DiscoveryError")


def test_discovers_windows_style_local_tree(tmp_path) -> None:
    source = tmp_path / "Residencia Presidencial de Olivos" / "2023"
    source.mkdir(parents=True)
    pdf = source / "10 de diciembre 2023.pdf"
    pdf.write_bytes(b"%PDF-fixture")

    files = discovery.discover(str(tmp_path))

    assert len(files) == 1
    assert files[0].location == "olivos"
    assert files[0].year == 2023
    assert files[0].month == 12
    assert files[0].url == pdf.as_uri()
