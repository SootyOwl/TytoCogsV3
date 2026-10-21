"""Network boundary regressions for PDF summarization."""

import base64
import threading
from types import SimpleNamespace

import httpx
import pytest

from tldscience.tldscience import TLDScience


@pytest.mark.parametrize("attachment", [False, True])
async def test_pdf_requests_do_not_block_discord(attachment, mocker):
    loop_thread = threading.get_ident()
    url = "https://example.com/paper.pdf"
    pdf = b"%PDF-1.7 test content"

    def head(request_url):
        assert threading.get_ident() != loop_thread
        assert request_url == url
        return httpx.Response(200, headers={"content-type": "application/pdf"})

    def get(request_url):
        assert threading.get_ident() != loop_thread
        assert request_url == url
        return httpx.Response(200, content=pdf)

    mocker.patch("tldscience.tldscience.httpx.head", side_effect=head)
    mocker.patch("tldscience.tldscience.httpx.get", side_effect=get)
    cog = object.__new__(TLDScience)
    cog.bot = SimpleNamespace(is_owner=mocker.AsyncMock(return_value=True))
    cog.generate_summary = mocker.AsyncMock(return_value="provider response")
    cog.extract_summary = mocker.AsyncMock(return_value="Summary")
    ctx = mocker.MagicMock()
    ctx.send = mocker.AsyncMock()
    ctx.message.attachments = (
        [SimpleNamespace(filename="paper.pdf", url=url)] if attachment else []
    )

    await TLDScience.summarize.callback(cog, ctx, url=None if attachment else url)

    cog.generate_summary.assert_awaited_once_with(
        base64.standard_b64encode(pdf).decode()
    )
    ctx.send.assert_awaited_once_with("Summary")
