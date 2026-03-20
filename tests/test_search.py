from unittest.mock import patch, MagicMock

def test_search_returns_five_results():
    fake_info = {
        "entries": [
            {"id": f"vid{i}", "title": f"Title {i}", "uploader": "Chan",
             "duration": 180, "thumbnail": "http://example.com/thumb.jpg"}
            for i in range(5)
        ]
    }
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.return_value = fake_info
        from downloader.search import search_youtube
        results = search_youtube("test query")
    assert len(results) == 5
    assert results[0]["title"] == "Title 0"
    assert "url" in results[0]

def test_search_returns_empty_on_error():
    with patch("yt_dlp.YoutubeDL") as MockYDL:
        instance = MockYDL.return_value.__enter__.return_value
        instance.extract_info.side_effect = Exception("network error")
        from downloader.search import search_youtube
        results = search_youtube("test query")
    assert results == []
