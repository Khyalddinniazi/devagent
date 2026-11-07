from textkit.text import camel_to_snake

def test_examples():
    assert camel_to_snake("parseHTTPResponse") == "parse_http_response"
    assert camel_to_snake("CamelCase") == "camel_case"
    assert camel_to_snake("getID") == "get_id"
    assert camel_to_snake("already_snake") == "already_snake"
    assert camel_to_snake("simple") == "simple"

def test_more():
    assert camel_to_snake("HTMLParser") == "html_parser"
    assert camel_to_snake("version2Update") == "version2_update"
