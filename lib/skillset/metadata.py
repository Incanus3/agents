import json
import os
import re
import stat
import unicodedata

from .layout import set_path, validate_layout, validate_set


TARGET_FIELD_PATTERN = re.compile(r"(name|description):[ \t]*(.*)\Z")


def normalize_scalar(value):
    return " ".join(value.split())


def parse_single_quoted(field, value):
    decoded = []
    index = 1
    while index < len(value):
        character = value[index]
        if character != "'":
            decoded.append(character)
            index += 1
        elif index + 1 < len(value) and value[index + 1] == "'":
            decoded.append("'")
            index += 2
        else:
            trailing = value[index + 1 :].strip()
            if trailing and not trailing.startswith("#"):
                return None, f"unsupported single-quoted {field}"
            return "".join(decoded), None
    return None, f"unterminated single-quoted {field}"


def closing_double_quote(value):
    escaped = False
    for index, character in enumerate(value[1:], start=1):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            return index
    return None


def strip_plain_comments(value):
    lines = []
    for line in value.splitlines():
        for index, character in enumerate(line):
            if character == "#" and (index == 0 or line[index - 1].isspace()):
                line = line[:index]
                break
        lines.append(line)
    return "\n".join(lines)


def parse_inline_scalar(field, raw):
    value = raw.strip()
    if not value:
        return None, f"empty {field}"
    if value.startswith("'"):
        value, reason = parse_single_quoted(field, value)
        if reason is not None:
            return None, reason
    elif value.startswith('"'):
        closing = closing_double_quote(value)
        if closing is None:
            return None, f"unterminated double-quoted {field}"
        trailing = value[closing + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            return None, f"unsupported double-quoted {field}"
        encoded = value[: closing + 1]
        encoded = encoded.replace("\r", "\\r").replace("\n", "\\n")
        encoded = encoded.replace("\t", "\\t")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError:
            return None, f"unsupported double-quoted {field}"
        if not isinstance(value, str):
            return None, f"unsupported double-quoted {field}"
    else:
        if value[0] in "[{&*!|>":
            return None, f"unsupported {field} scalar"
        value = strip_plain_comments(value)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None, f"unsupported unicode {field}"
    value = normalize_scalar(value)
    if not value:
        return None, f"empty {field}"
    return value, None


def collect_target_fields(lines):
    fields = {"name": [], "description": []}
    index = 0
    while index < len(lines):
        match = TARGET_FIELD_PATTERN.fullmatch(lines[index])
        index += 1
        if match is None:
            continue
        field, raw = match.groups()
        continuation = []
        while index < len(lines):
            line = lines[index]
            if line and not line[0].isspace():
                break
            continuation.append(line)
            index += 1
        if raw in ("|", ">"):
            fields[field].append(("block", "\n".join(continuation)))
        else:
            fields[field].append(("inline", "\n".join([raw, *continuation])))
    return fields


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return None, "invalid frontmatter opening delimiter"
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return None, "invalid frontmatter: missing closing delimiter"
    fields = collect_target_fields(lines[1:closing])
    for field in ("name", "description"):
        if not fields[field]:
            return None, f"missing {field}"
        if len(fields[field]) != 1:
            return None, f"duplicate {field}"
    metadata = {}
    for field in ("name", "description"):
        form, raw = fields[field][0]
        if form == "block":
            value = normalize_scalar(raw)
            reason = None if value else f"empty {field}"
        else:
            value, reason = parse_inline_scalar(field, raw)
        if reason is not None:
            return None, reason
        metadata[field] = value
    return metadata, None


def read_skill_text(directory):
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        directory_fd = os.open(directory, directory_flags)
    except OSError:
        return None, "unsupported skill directory"
    try:
        try:
            metadata = os.stat("SKILL.md", dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None, "missing SKILL.md"
        except OSError:
            return None, "unsupported SKILL.md"
        if stat.S_ISLNK(metadata.st_mode):
            return None, "unsupported SKILL.md symlink"
        if not stat.S_ISREG(metadata.st_mode):
            return None, "unsupported SKILL.md file type"
        try:
            file_fd = os.open("SKILL.md", file_flags, dir_fd=directory_fd)
        except OSError:
            return None, "unsupported SKILL.md"
        try:
            chunks = []
            while True:
                chunk = os.read(file_fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError:
            return None, "unsupported SKILL.md read"
        finally:
            os.close(file_fd)
        try:
            return b"".join(chunks).decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "invalid UTF-8 in SKILL.md"
    finally:
        os.close(directory_fd)


def inspect_skills(skills):
    inspected = []
    for candidate in sorted(skills.iterdir(), key=lambda path: path.name):
        try:
            mode = candidate.lstat().st_mode
        except OSError:
            inspected.append((candidate.name, None, None, "unsupported candidate"))
            continue
        if stat.S_ISREG(mode):
            continue
        if stat.S_ISLNK(mode):
            inspected.append(
                (candidate.name, None, None, "unsupported skill directory symlink")
            )
            continue
        if not stat.S_ISDIR(mode):
            continue
        text, reason = read_skill_text(candidate)
        metadata = None
        if reason is None:
            metadata, reason = parse_frontmatter(text)
        if reason is None:
            inspected.append(
                (candidate.name, metadata["name"], metadata["description"], None)
            )
        else:
            inspected.append((candidate.name, None, None, reason))
    return inspected


def list_sets(root, verbose):
    active_name = validate_layout(root)
    names = sorted(entry.name for entry in (root / "skillsets").iterdir())
    for name in names:
        marker = "* " if name == active_name else ""
        line = f"{marker}{name}"
        if verbose:
            skills = inspect_skills(set_path(root, name) / "skills")
            declared = sorted(
                printable_text(name)
                for _directory, name, _description, reason in skills
                if reason is None
            )
            line += "\t" + (", ".join(declared) if declared else "(no skills)")
        print(line)


def current(root):
    print(validate_layout(root))


def show(root, name):
    validate_layout(root)
    skills = validate_set(root, name) / "skills"
    lines = []
    for directory, declared, description, reason in inspect_skills(skills):
        if reason is None:
            lines.append(
                f"{printable_text(declared)} — {printable_text(description)}"
            )
        else:
            lines.append(f"{printable_text(directory)} — [invalid: {reason}]")
    for line in sorted(lines):
        print(line)


def printable_text(value):
    displayed = []
    for character in str(value):
        codepoint = ord(character)
        if unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}:
            if codepoint <= 0xFF:
                displayed.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                displayed.append(f"\\u{codepoint:04x}")
            else:
                displayed.append(f"\\U{codepoint:08x}")
        else:
            displayed.append(character)
    return "".join(displayed).encode(
        "utf-8", "backslashreplace"
    ).decode("utf-8")
