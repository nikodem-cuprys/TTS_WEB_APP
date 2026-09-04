from app.text.segment import pack_chunks, segment_text, split_sentences


def test_split_sentences_basic():
    text = "It was a dark night. The wind howled loudly! Was she afraid?"
    assert split_sentences(text) == [
        "It was a dark night.",
        "The wind howled loudly!",
        "Was she afraid?",
    ]


def test_split_sentences_empty_text():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_pack_chunks_merges_short_sentences():
    sentences = ["Hi.", "Go now.", "Wait.", "Stop.", "Look out!", "Run fast.", "Come here.", "Sit down."]
    chunks = pack_chunks(sentences, max_chars=30)
    assert all(len(c) <= 30 for c in chunks)
    assert " ".join(sentences) == " ".join(chunks)  # no words lost or reordered


def test_pack_chunks_never_splits_a_single_long_sentence():
    long_sentence = (
        "This is a single very long sentence that goes on and on without any "
        "punctuation breaks whatsoever until finally it ends here."
    )
    chunks = pack_chunks([long_sentence], max_chars=50)
    assert chunks == [long_sentence]  # kept whole even though it exceeds max_chars


def test_segment_text_end_to_end():
    text = "One sentence here. Another sentence follows. And a third one too."
    chunks = segment_text(text, max_chars=1000)
    assert chunks == [text]  # fits comfortably in a single chunk


def test_segment_text_respects_max_chars_with_multiple_sentences():
    text = (
        "The wind howled through the trees, carrying with it the scent of rain. "
        "She walked slowly toward the old house, unsure of what awaited her inside. "
        "The door creaked open on its own, revealing a dark hallway beyond."
    )
    chunks = segment_text(text, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 or c.count(".") <= 1 for c in chunks)  # oversized only for single sentences


def test_chinese_sentences_split_on_full_width_terminators():
    text = "你好，世界。这是第一句话！这是第二句话？"
    assert split_sentences(text, language="zh") == ["你好，世界。", "这是第一句话！", "这是第二句话？"]


def test_chinese_chunks_join_without_a_space():
    # Chinese doesn't separate sentences with spaces the way English does — packing
    # two sentences into one chunk with pack_chunks' default " " joiner would insert
    # an ASCII space foreign to the script; segment_text must use "" for zh instead.
    text = "你好，世界。这是第一句话！"
    chunks = segment_text(text, language="zh", max_chars=1000)
    assert chunks == ["你好，世界。这是第一句话！"]
    assert " " not in chunks[0]


def test_pack_chunks_custom_joiner():
    chunks = pack_chunks(["你好。", "再见。"], max_chars=1000, joiner="")
    assert chunks == ["你好。再见。"]
