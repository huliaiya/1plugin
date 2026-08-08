"""serializer.py 单元测试"""

import json

from astrbot_plugin_fox_toolbox.fox_toolbox.serializer import (
    serialize_component,
    serialize_message_chain,
    extract_reply_info,
    extract_media_url,
    compute_content_hash,
    extract_media_paths,
    MEDIA_COMPONENT_TYPES,
    COMPONENT_TYPE_MEDIA_MAP,
    ALL_KNOWN_COMPONENT_TYPES,
)


class MockComponent:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class TestSerializeComponent:
    def test_plain_text(self):
        comp = MockComponent(text="hello")
        comp.__class__.__name__ = "Plain"
        result = serialize_component(comp)
        assert result["type"] == "Plain"
        assert result["text"] == "hello"

    def test_image_with_url(self):
        comp = MockComponent(url="http://example.com/img.png", file="img.png", width=100, height=200)
        comp.__class__.__name__ = "Image"
        result = serialize_component(comp)
        assert result["type"] == "Image"
        assert result["url"] == "http://example.com/img.png"
        assert result["width"] == 100
        assert result["height"] == 200

    def test_at_component(self):
        comp = MockComponent(user_id="12345", name="Alice")
        comp.__class__.__name__ = "At"
        result = serialize_component(comp)
        assert result["type"] == "At"
        assert result["user_id"] == "12345"
        assert result["name"] == "Alice"

    def test_reply_component(self):
        comp = MockComponent(message_id="999", sender_id="u1", text="original")
        comp.__class__.__name__ = "Reply"
        result = serialize_component(comp)
        assert result["type"] == "Reply"
        assert result["message_id"] == "999"

    def test_skip_none_values(self):
        comp = MockComponent(text="hi", optional_field=None)
        comp.__class__.__name__ = "Plain"
        result = serialize_component(comp)
        assert "optional_field" not in result

    def test_skip_callable(self):
        comp = MockComponent(text="hi")
        comp.__class__.__name__ = "Plain"
        result = serialize_component(comp)
        for key in result:
            if key == "type":
                continue
            assert not callable(result[key])

    def test_nested_list_serialization(self):
        comp = MockComponent(nodes=[{"id": 1}, {"id": 2}])
        comp.__class__.__name__ = "Forward"
        result = serialize_component(comp)
        assert result["nodes"] == [{"id": 1}, {"id": 2}]


class TestSerializeMessageChain:
    def test_empty_chain(self):
        assert serialize_message_chain([]) == []
        assert serialize_message_chain(None) == []

    def test_valid_chain(self):
        class PlainComp:
            pass
        PlainComp.__name__ = "Plain"
        p = PlainComp()
        p.text = "hello"

        class ImageComp:
            pass
        ImageComp.__name__ = "Image"
        i = ImageComp()
        i.url = "http://x.com/i.png"

        result = serialize_message_chain([p, i])
        assert len(result) == 2
        assert result[0]["type"] == "Plain"
        assert result[1]["type"] == "Image"

    def test_serialize_error_fallback(self):
        class BadComponent:
            pass
        BadComponent.__name__ = "Bad"
        bc = BadComponent()
        bc.__class__.__name__ = "Bad"
        result = serialize_message_chain([bc])
        assert len(result) == 1
        assert result[0]["type"] == "Bad"


class TestExtractReplyInfo:
    def test_with_message_id(self):
        chain = [{"type": "Plain", "text": "hi"}, {"type": "Reply", "message_id": "123"}]
        assert extract_reply_info(chain) == "123"

    def test_with_id_fallback(self):
        chain = [{"type": "Reply", "id": "456"}]
        assert extract_reply_info(chain) == "456"

    def test_no_reply(self):
        chain = [{"type": "Plain", "text": "hi"}]
        assert extract_reply_info(chain) is None

    def test_empty_chain(self):
        assert extract_reply_info([]) is None

    def test_non_dict_items(self):
        chain = ["not a dict", 123, {"type": "Reply", "message_id": "789"}]
        assert extract_reply_info(chain) == "789"


class TestExtractMediaUrl:
    def test_url_field(self):
        assert extract_media_url({"type": "Image", "url": "http://example.com/img.png"}) == "http://example.com/img.png"

    def test_file_field_http(self):
        assert extract_media_url({"type": "Image", "file": "http://example.com/file.jpg"}) == "http://example.com/file.jpg"

    def test_path_field_http(self):
        assert extract_media_url({"type": "Record", "path": "http://example.com/audio.mp3"}) == "http://example.com/audio.mp3"

    def test_no_url(self):
        assert extract_media_url({"type": "Plain", "text": "hello"}) is None

    def test_local_path(self):
        # 放宽后：本地路径也会被返回，交由下载器判断
        assert extract_media_url({"type": "Image", "url": "/local/path/img.png"}) == "/local/path/img.png"

    def test_non_http_url(self):
        # 放宽后：data: URI 也会被返回
        assert extract_media_url({"type": "Image", "url": "data:image/png;base64,abc"}) == "data:image/png;base64,abc"

    def test_file_uri(self):
        assert extract_media_url({"type": "Image", "url": "file:///C:/Users/x/img.png"}) == "file:///C:/Users/x/img.png"

    def test_base64_payload(self):
        assert extract_media_url({"type": "Image", "file": "base64://aGVsbG8="}) == "base64://aGVsbG8="

    def test_bare_filename_fallback(self):
        # url 为空时回退到 file 字段（裸文件名也返回）
        assert extract_media_url({"type": "Image", "url": "", "file": "abc123.image"}) == "abc123.image"

    def test_priority_url_over_file(self):
        assert extract_media_url({"type": "Image", "url": "http://a.com/1.png", "file": "x.png"}) == "http://a.com/1.png"

    def test_empty_string_values_skipped(self):
        assert extract_media_url({"type": "Image", "url": "", "file": "", "path": ""}) is None


class TestComputeContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("tg", "sess1", "user1", "hello", 1700000000000)
        h2 = compute_content_hash("tg", "sess1", "user1", "hello", 1700000000000)
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = compute_content_hash("tg", "sess1", "user1", "hello", 1700000000000)
        h2 = compute_content_hash("tg", "sess1", "user1", "world", 1700000000000)
        assert h1 != h2

    def test_hash_length(self):
        h = compute_content_hash("tg", "s", "u", "m", 1700000000000)
        assert len(h) == 16

    def test_none_message_str(self):
        h = compute_content_hash("tg", "s", "u", None, 1700000000000)
        assert len(h) == 16

    def test_different_millisecond_same_second(self):
        h1 = compute_content_hash("tg", "s", "u", "m", 1700000000000)
        h2 = compute_content_hash("tg", "s", "u", "m", 1700000000999)
        assert h1 != h2

    def test_second_precision_timestamp(self):
        h1 = compute_content_hash("tg", "s", "u", "m", 1700000000000)
        h2 = compute_content_hash("tg", "s", "u", "m", 1700000001000)
        assert h1 != h2


class TestExtractMediaPaths:
    def test_valid_chain(self):
        chain = [
            {"type": "Plain", "text": "hi"},
            {"type": "Image", "url": "http://x.com/i.png", "local_path": "images/2026-04/abc.jpg"},
            {"type": "Record", "local_path": "records/2026-04/def.mp3"},
        ]
        result = extract_media_paths(json.dumps(chain))
        assert result == ["images/2026-04/abc.jpg", "records/2026-04/def.mp3"]

    def test_no_local_path(self):
        chain = [{"type": "Plain", "text": "hi"}]
        result = extract_media_paths(json.dumps(chain))
        assert result == []

    def test_none_input(self):
        assert extract_media_paths(None) == []

    def test_empty_string(self):
        assert extract_media_paths("") == []

    def test_invalid_json(self):
        assert extract_media_paths("not json") == []

    def test_non_list_json(self):
        assert extract_media_paths('{"key": "value"}') == []

    def test_empty_local_path(self):
        chain = [{"type": "Image", "local_path": ""}]
        assert extract_media_paths(json.dumps(chain)) == []

    def test_non_string_local_path(self):
        chain = [{"type": "Image", "local_path": 123}]
        assert extract_media_paths(json.dumps(chain)) == []


class TestConstants:
    def test_media_types(self):
        assert "Image" in MEDIA_COMPONENT_TYPES
        assert "Record" in MEDIA_COMPONENT_TYPES
        assert "Video" in MEDIA_COMPONENT_TYPES
        assert "File" in MEDIA_COMPONENT_TYPES

    def test_media_map(self):
        assert COMPONENT_TYPE_MEDIA_MAP["Image"] == "images"
        assert COMPONENT_TYPE_MEDIA_MAP["Record"] == "records"
        assert COMPONENT_TYPE_MEDIA_MAP["Video"] == "videos"
        assert COMPONENT_TYPE_MEDIA_MAP["File"] == "files"

    def test_all_known_types(self):
        assert "Plain" in ALL_KNOWN_COMPONENT_TYPES
        assert "Image" in ALL_KNOWN_COMPONENT_TYPES
        assert "At" in ALL_KNOWN_COMPONENT_TYPES
        assert "Reply" in ALL_KNOWN_COMPONENT_TYPES
