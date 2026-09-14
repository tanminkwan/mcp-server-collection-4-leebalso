"""MCP 서버 테스트."""

import json
from unittest.mock import patch

import httpx
import pytest
import respx

from error_rag_mcp.server import create_server, create_rag_client
from mcp_common.config import MAX_RESPONSE_BYTES_ENV
from mcp_common.response_limit import ResponseTooLargeError


@pytest.fixture(autouse=True)
def _suppress_dotenv():
    """테스트 중 .env 파일 로드를 차단한다."""
    with patch("error_rag_mcp.config.load_dotenv"):
        yield


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("RAG_API_BASE_URL", "http://localhost:28000")
    monkeypatch.setenv("RAG_COLLECTION_NAME", "error_rag_test")
    monkeypatch.setenv("RAG_DOMAIN_ID", "6")
    monkeypatch.delenv("RAG_API_BEARER_TOKEN", raising=False)
    monkeypatch.delenv(MAX_RESPONSE_BYTES_ENV, raising=False)


@pytest.fixture()
def mcp(_env):
    return create_server()


@pytest.fixture()
def client(_env):
    return create_rag_client()


SEARCH_URL = "http://localhost:28000/api/rag/search"
KNOWLEDGE_URL = "http://localhost:28000/api/rag/knowledge"


def _search_side_effect(vector_results, text_matching_results):
    def _handler(request):
        payload = json.loads(request.content)
        if payload["search_method"] == "vector":
            return httpx.Response(200, json=vector_results)
        return httpx.Response(200, json=text_matching_results)

    return _handler


class TestCreateServer:
    """서버 생성 테스트."""

    def test_server_name(self, mcp):
        """서버 이름이 올바르게 설정된다."""
        assert mcp.name == "error-rag-mcp"

    def test_server_has_tools(self, mcp):
        """검색/등록 도구가 등록되어 있다."""
        tool_names = list(mcp._tool_manager._tools.keys())
        assert "search_similar_error" in tool_names
        assert "register_error_resolution" in tool_names


class TestSearchSimilarErrorTool:
    """search_similar_error 도구 테스트."""

    @respx.mock
    async def test_merges_vector_and_text_matching_results(self, mcp, _env):
        """벡터 검색과 텍스트 매칭 검색 결과를 병합해 반환한다."""
        vector_results = [
            {"id": "a", "collection": "c", "score": 0.9, "content": "x",
             "extended_content": "x", "domain_id": 6, "source": "s",
             "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        text_matching_results = [
            {"id": "b", "collection": "c", "score": 1.0, "content": "y",
             "extended_content": "y", "domain_id": 6, "source": "s",
             "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        respx.post(SEARCH_URL).mock(
            side_effect=_search_side_effect(vector_results, text_matching_results)
        )

        tool_fn = mcp._tool_manager._tools["search_similar_error"].fn
        result_json = await tool_fn(error_summary="요약", error_keyword="ORA-00001")
        result = json.loads(result_json)

        assert [item["id"] for item in result] == ["a", "b"]

    @respx.mock
    async def test_dedupes_overlapping_ids_keeping_vector_first(self, mcp, _env):
        """동일 id가 양쪽에서 나오면 벡터 검색 결과를 우선하고 한 번만 포함한다."""
        shared = {
            "id": "dup-1", "collection": "c", "score": 0.5, "content": "vector-content",
            "extended_content": "x", "domain_id": 6, "source": "s",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        duplicate_in_text = {**shared, "content": "text-matching-content", "score": 1.0}
        respx.post(SEARCH_URL).mock(
            side_effect=_search_side_effect([shared], [duplicate_in_text])
        )

        tool_fn = mcp._tool_manager._tools["search_similar_error"].fn
        result = json.loads(await tool_fn(error_summary="요약", error_keyword="dup"))

        assert len(result) == 1
        assert result[0]["content"] == "vector-content"

    @respx.mock
    async def test_no_results_returns_empty_list(self, mcp, _env):
        """검색 결과가 전혀 없으면 빈 배열 문자열을 반환한다."""
        respx.post(SEARCH_URL).mock(side_effect=_search_side_effect([], []))

        tool_fn = mcp._tool_manager._tools["search_similar_error"].fn
        result = json.loads(await tool_fn(error_summary="요약", error_keyword="없음"))

        assert result == []

    @respx.mock
    async def test_blank_keyword_skips_text_matching_search(self, mcp, _env):
        """error_keyword가 빈 문자열이면 text_matching 검색을 건너뛰고 벡터 검색만 수행한다."""
        vector_results = [
            {"id": "a", "collection": "c", "score": 0.9, "content": "x",
             "extended_content": "x", "domain_id": 6, "source": "s",
             "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        route = respx.post(SEARCH_URL).mock(
            return_value=httpx.Response(200, json=vector_results)
        )

        tool_fn = mcp._tool_manager._tools["search_similar_error"].fn
        result = json.loads(await tool_fn(error_summary="요약", error_keyword=""))

        assert result == vector_results
        assert route.call_count == 1
        payload = json.loads(route.calls.last.request.read())
        assert payload["search_method"] == "vector"

    @respx.mock
    async def test_search_api_error_returns_error_message(self, mcp, _env):
        """검색 API 오류 시 오류 메시지를 반환한다."""
        respx.post(SEARCH_URL).mock(return_value=httpx.Response(500))

        tool_fn = mcp._tool_manager._tools["search_similar_error"].fn
        result = await tool_fn(error_summary="요약", error_keyword="ORA-00001")

        assert "오류 검색 오류" in result


class TestRegisterErrorResolutionTool:
    """register_error_resolution 도구 테스트."""

    @respx.mock
    async def test_register_success(self, mcp, _env):
        """정상 입력 시 등록에 성공하고 결과를 반환한다."""
        route = respx.post(KNOWLEDGE_URL).mock(
            return_value=httpx.Response(
                200,
                json={"id": "point-1", "status": "success",
                      "created_at": "2026-09-03T00:00:00+00:00"},
            )
        )

        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="DB 커넥션 풀 고갈로 응답 지연 발생",
            error_keyword=["ORA-00001", "CONN_POOL_EXHAUSTED"],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="DB 커넥션 풀 고갈",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="커넥션 풀 크기 확장",
        )

        assert "success" in result
        payload = json.loads(route.calls.last.request.read())
        assert payload["content"] == (
            "DB 커넥션 풀 고갈로 응답 지연 발생 [ORA-00001, CONN_POOL_EXHAUSTED]"
        )
        assert payload["extended_content"] == (
            "# 오류 및 조치 보고서\n"
            "\n"
            "### 1. 오류 발생일시\n"
            "2026-09-03 10:00:00\n"
            "\n"
            "### 2. 오류 발생 위치\n"
            "pcbkaa11 / ONL_MS12\n"
            "\n"
            "### 3. 오류 내용\n"
            "DB 커넥션 풀 고갈\n"
            "\n"
            "### 4. 조치일시\n"
            "2026-09-03 10:30:00\n"
            "\n"
            "### 5. 조치자\n"
            "김철수\n"
            "\n"
            "### 6. 조치 내용\n"
            "커넥션 풀 크기 확장"
        )
        assert payload["source"] == "error-resolution-report"

    async def test_error_summary_too_long_is_rejected(self, mcp, _env):
        """error_summary가 300자를 초과하면 등록을 거부한다."""
        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="가" * 301,
            error_keyword=["ORA-00001"],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="상세",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="조치",
        )

        assert "300자" in result

    async def test_error_keyword_empty_is_rejected(self, mcp, _env):
        """error_keyword가 비어 있으면 등록을 거부한다."""
        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="요약",
            error_keyword=[],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="상세",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="조치",
        )

        assert "error_keyword" in result

    async def test_error_keyword_over_max_count_is_rejected(self, mcp, _env):
        """error_keyword가 4개 이상이면 등록을 거부한다."""
        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="요약",
            error_keyword=["A", "B", "C", "D"],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="상세",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="조치",
        )

        assert "error_keyword" in result

    async def test_error_keyword_with_blank_entry_is_rejected(self, mcp, _env):
        """error_keyword 목록에 빈 문자열이 있으면 등록을 거부한다."""
        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="요약",
            error_keyword=["ORA-00001", "  "],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="상세",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="조치",
        )

        assert "error_keyword" in result

    @respx.mock
    async def test_register_api_error_returns_error_message(self, mcp, _env):
        """등록 API 오류 시 오류 메시지를 반환한다."""
        respx.post(KNOWLEDGE_URL).mock(return_value=httpx.Response(500))

        tool_fn = mcp._tool_manager._tools["register_error_resolution"].fn
        result = await tool_fn(
            error_summary="요약",
            error_keyword=["ORA-00001"],
            error_occurred_at="2026-09-03 10:00:00",
            host_id="pcbkaa11",
            was_instance_id="ONL_MS12",
            error_content="상세",
            action_taken_at="2026-09-03 10:30:00",
            actor="김철수",
            action_content="조치",
        )

        assert "오류 조치 결과 등록 오류" in result


class TestResponseSizeLimit:
    """응답 크기 제한 테스트."""

    @respx.mock
    async def test_oversized_search_result_raises_error(self, monkeypatch, _env):
        """검색 결과가 한도를 넘으면 잘리지 않고 '너무 크다'는 오류로 반환된다."""
        monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV, "100")
        huge = [
            {"id": "a", "collection": "c", "score": 0.9, "content": "x" * 5000,
             "extended_content": "y" * 5000, "domain_id": 6, "source": "s",
             "created_at": "2026-01-01T00:00:00+00:00"},
        ]
        respx.post(SEARCH_URL).mock(side_effect=_search_side_effect(huge, []))

        tool_fn = create_server()._tool_manager._tools["search_similar_error"].fn
        with pytest.raises(ResponseTooLargeError) as exc_info:
            await tool_fn(error_summary="요약", error_keyword="")
        assert "너무 커서" in str(exc_info.value)

    @respx.mock
    async def test_result_within_limit_passes_through(self, _env):
        """기본 한도(30KB) 이내 응답은 그대로 반환된다."""
        respx.post(SEARCH_URL).mock(side_effect=_search_side_effect([], []))

        tool_fn = create_server()._tool_manager._tools["search_similar_error"].fn
        assert json.loads(await tool_fn(error_summary="요약", error_keyword="")) == []
