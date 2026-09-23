from app.guardrails import validate_reply

TOOLS = [{"resultados": [{"sku": "T2S-VER-FG", "precio_cop": 183500}]}]


def test_allows_verified_price():
    assert validate_reply("El T2 Speed cuesta $183.500", TOOLS) == []


def test_blocks_invented_price():
    v = validate_reply("El T2 Speed cuesta $150.000", TOOLS)
    assert v and v[0].startswith("precio_no_verificado")


def test_blocks_invented_sku():
    assert any(x.startswith("sku_no_verificado") for x in validate_reply("Pide el T2S-AZU-FG", TOOLS))


def test_ignores_centimeters_and_small_numbers():
    assert validate_reply("Tu pie mide 26,5 cm, te va la talla 41", TOOLS) == []



def test_blocks_size_without_tool():
    v = validate_reply("En este modelo te recomendaria la talla *41*.", TOOLS, ["search_products"])
    assert any(x.startswith("talla_no_verificada") for x in v)


def test_allows_size_with_tool():
    assert validate_reply("Te recomiendo la talla 41.", TOOLS, ["recommend_size"]) == []


def test_size_mentions_without_recommendation_are_ok():
    assert validate_reply("Tenemos tallas 7 a 10 y hay talla 44 agotada.", TOOLS, ["search_products"]) == []