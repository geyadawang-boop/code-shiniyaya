"""
Chinese text processing utilities — adapted from subbatch-local's smart segmentation.
Provides intelligent sentence splitting, recursive chunk splitting, optimal break
point finding, two-pass merging, and deduplication for Chinese subtitle text.
"""
import re


def smart_split_sentences(text, max_len=18):
    """Split Chinese text at natural sentence boundaries, then at clause boundaries.
    Port of subbatch-local's xt() function — produces ~18 char lines."""
    if not text:
        return []
    # Split at sentence-ending punctuation (NOT semicolons -- those are clause-level)
    sentences = re.split(r'(?<=[。！？!?])', text)
    result = []
    for sentence in sentences:
        if not sentence.strip():
            continue
        if len(sentence) <= max_len:
            result.append(sentence)
        else:
            # Further split at clause boundaries (commas AND semicolons)
            clauses = re.split(r'(?<=[，,、；;])', sentence)
            for clause in clauses:
                if not clause.strip():
                    continue
                if len(clause) <= max_len:
                    result.append(clause)
                else:
                    result.extend(_recursive_split(clause, max_len))
    return _two_pass_merge(result, min(20, max_len + 2))


def _recursive_split(text, max_len=18):
    """Recursively split long text at optimal break points."""
    if len(text) <= max_len:
        return [text]
    min_len = min(18, max(16, max_len - 1))
    result = []
    remaining = text
    while len(remaining) > max_len:
        bp = _find_optimal_break(remaining, max_len, min_len)
        chunk = remaining[:bp].strip()
        if chunk:
            result.append(chunk)
        remaining = remaining[bp:].strip()
        if not remaining:
            break
    if remaining:
        result.append(remaining)
    return result


def _find_optimal_break(text, max_len=18, min_len=16):
    """Find the best position to break a long Chinese text line.
    Scores candidate break points based on punctuation, transition words,
    and structural particles."""
    if len(text) <= max_len:
        return len(text)

    candidates = []
    # Collect candidate break positions
    for i in range(min_len, min(max_len + 1, len(text))):
        char = text[i - 1] if i > 0 else ''
        candidates.append((i, _score_break(text, i)))

    if candidates:
        candidates.sort(key=lambda x: -x[1])
        best = candidates[0]
        if best[1] > 0:
            return best[0]

    # Fallback: minimize asymmetry
    best_pos = max_len
    best_asym = abs(len(text) - 2 * max_len)
    for i in range(min_len, min(max_len + 1, len(text) - 1)):
        asym = abs(len(text[i:]) - i)
        if asym < best_asym:
            best_asym = asym
            best_pos = i

    return best_pos or max_len


def _score_break(text, pos):
    """Score a candidate break position."""
    score = 0
    char_at_break = text[pos - 1] if pos > 0 else ''
    char_after = text[pos] if pos < len(text) else ''

    # Punctuation bonuses
    if char_at_break in '。！？!?；;':
        score += 120
    elif char_at_break in '，,、：:':
        score += 70

    # Length bonus: 12-18 chars is ideal
    if 12 <= pos <= 18:
        score += 20

    # Transition word bonus (char after break starts with transition)
    transition_starts = {'但', '不', '然', '所', '因', '如', '虽', '只', '还', '就', '可', '而', '则'}
    if char_after in transition_starts:
        score += 45

    # Penalties for extremely short segments
    if pos <= 2 or (len(text) - pos) <= 2:
        score -= 160
    elif pos <= 4 or (len(text) - pos) <= 4:
        score -= 90

    # Structural particle penalty
    particles = {'的', '了', '着', '过', '地', '得', '们'}
    if char_at_break in particles:
        score -= 90

    return score


def _two_pass_merge(chunks, max_len=20):
    """Two-pass forward merge to combine orphaned short chunks."""
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        return chunks

    # Pass 1
    result = _merge_pass(chunks, max_len)
    # Pass 2
    return _merge_pass(result, max_len)


def _merge_pass(chunks, max_len=20):
    """Single pass merge: combine short chunks backward or forward."""
    result = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]

        # Try merge backward
        if result and _should_merge_back(chunk, result[-1], max_len):
            result[-1] = result[-1] + chunk
            i += 1
            continue

        # Try merge forward
        if i + 1 < len(chunks) and _should_merge_forward(chunk, chunks[i + 1], max_len):
            result.append(chunk + chunks[i + 1])
            i += 2
            continue

        result.append(chunk)
        i += 1

    return result


def _should_merge_back(chunk, prev, max_len):
    """Check if chunk should be merged backward into previous."""
    if len(chunk) <= 2 and len(prev) + len(chunk) <= max_len - 2:
        if not prev.endswith(('。', '！', '？', '!', '?', '；', ';')):
            return True
    if len(chunk) <= 4 and chunk[0] in '的了吗呢吧啊嗯哦么这那':
        if (len(prev) + len(chunk) <= max_len and
                not prev.endswith(('。', '！', '？', '!', '?', '；', ';'))):
            return True
    return False


def _should_merge_forward(chunk, next_chunk, max_len):
    """Check if chunk should be merged forward with next."""
    if len(chunk) <= 4:
        if chunk[-1] in '的了吗呢吧啊嗯哦么' and len(chunk) + len(next_chunk) <= max_len:
            return True
    return False


def remove_duplicate_lines(text):
    """Remove duplicate/similar lines from Chinese subtitle text."""
    lines = text.strip().split('\n')
    seen = []
    result = []
    for line in lines:
        stripped = re.sub(r'[\s\W]', '', line)
        if not stripped:
            continue
        # Check last 3 lines for duplicates
        is_dup = False
        for prev in seen[-3:]:
            prev_stripped = re.sub(r'[\s\W]', '', prev)
            if stripped == prev_stripped:
                is_dup = True
                break
            # Check similarity -- threshold lowered from 0.7 to 0.95 for Chinese
            # because function characters (的了是在我等) cause false positives
            if len(stripped) >= 10 and len(prev_stripped) >= 10:
                len_ratio = min(len(stripped), len(prev_stripped)) / max(len(stripped), len(prev_stripped))
                if len_ratio < 0.7:
                    continue  # Too different in length to be duplicates
                overlap = len(set(stripped) & set(prev_stripped))
                similarity = overlap / max(len(stripped), len(prev_stripped))
                if similarity > 0.95:
                    is_dup = True
                    break
        if not is_dup:
            result.append(line)
            seen.append(line)
    return '\n'.join(result)


def clean_chinese_text(text, min_len=18):
    """Main entry point: clean and format Chinese subtitle text.
    Removes whisper timestamp tokens, normalizes whitespace,
    applies smart sentence splitting, and deduplicates lines."""
    if not text:
        return text

    # Remove whisper timestamp tokens like <|12.34|>
    text = re.sub(r"<\|\d+\.\d+\|>", "", text)
    # Remove replacement character
    text = text.replace("�", "")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Smart Chinese sentence splitting
    lines = smart_split_sentences(text, min_len)

    # Deduplicate
    result = remove_duplicate_lines("\n".join(lines))

    return result
