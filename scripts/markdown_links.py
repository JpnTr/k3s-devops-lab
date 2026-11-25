"""Small Markdown heading-anchor helper for repository link validation."""
import re


def heading_anchors(markdown):
    """Return GitHub-style anchors for ATX headings outside fenced code blocks."""
    anchors, counts, fence_char, fence_len = set(), {}, None, 0
    for line in markdown.splitlines():
        fence = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if fence and fence_char is None:
            marker, info = fence.group(1, 2)
            if marker[0] != "`" or "`" not in info:
                fence_char, fence_len = marker[0], len(marker)
                continue
        elif fence_char is not None:
            marker, trailing = fence.group(1, 2) if fence else ("", "")
            if marker and marker[0] == fence_char and len(marker) >= fence_len and not trailing.strip():
                fence_char, fence_len = None, 0
            continue

        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        heading = re.sub(r"`([^`]*)`", r"\1", match.group(2))
        heading = re.sub(r"<[^>]*>", "", heading).lower()
        slug = re.sub(r"[^\w -]", "", heading, flags=re.UNICODE)
        slug = re.sub(r"[\s]+", "-", slug).strip("-")
        if not slug:
            continue
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors
