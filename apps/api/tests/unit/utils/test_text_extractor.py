import io
from app.services.text_extractor import extract_text
from app.services.text_normalizer import normalize_text

def test_txt_basic():
    data = "Привет, мир!\nСтрока 2".encode("utf-8")
    res = extract_text(data, "note.txt")
    assert "Привет" in res.text
    assert res.kind.startswith("txt")

def test_csv_basic():
    data = b"a,b,c\n1,2,3\n4,5,6\n"
    res = extract_text(data, "table.csv")
    assert "1\t2\t3" in res.text

def test_normalize_hyphen_wrap():
    raw = "слово-\nперенос"
    norm = normalize_text(raw)
    # Проверяем, что дефис и перенос строки обработаны
    assert "слово" in norm and "перенос" in norm
    # Перенос строки должен быть удален, дефис может остаться
    assert "\n" not in norm
