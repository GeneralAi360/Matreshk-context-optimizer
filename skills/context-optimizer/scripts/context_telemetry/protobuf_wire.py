from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class ProtoField:
    number: int
    wire_type: int
    value: int | None = None
    data: bytes | None = None


def read_varint(data: bytes, offset: int = 0) -> tuple[int, int] | None:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
        shift += 7
        if shift > 70:
            return None
    return None


def parse_fields(data: bytes) -> list[ProtoField]:
    fields: list[ProtoField] = []
    offset = 0
    while offset < len(data):
        key = read_varint(data, offset)
        if key is None:
            break
        raw_key, offset = key
        number = raw_key >> 3
        wire_type = raw_key & 0x07
        if number <= 0:
            break

        if wire_type == 0:
            value = read_varint(data, offset)
            if value is None:
                break
            raw_value, offset = value
            fields.append(ProtoField(number, wire_type, value=raw_value))
            continue

        if wire_type == 1:
            end = offset + 8
            if end > len(data):
                break
            fields.append(ProtoField(number, wire_type, data=data[offset:end]))
            offset = end
            continue

        if wire_type == 2:
            length = read_varint(data, offset)
            if length is None:
                break
            size, offset = length
            if size < 0:
                break
            end = offset + size
            if end > len(data):
                break
            fields.append(ProtoField(number, wire_type, data=data[offset:end]))
            offset = end
            continue

        if wire_type == 5:
            end = offset + 4
            if end > len(data):
                break
            fields.append(ProtoField(number, wire_type, data=data[offset:end]))
            offset = end
            continue

        # Groups (3/4) and unknown wire types are intentionally unsupported.
        break
    return fields


def first(fields: Iterable[ProtoField], number: int) -> ProtoField | None:
    for field in fields:
        if field.number == number:
            return field
    return None


def all_fields(fields: Iterable[ProtoField], number: int) -> list[ProtoField]:
    return [field for field in fields if field.number == number]


def field_bytes(field: ProtoField | None) -> bytes | None:
    return field.data if field is not None else None


def field_text(field: ProtoField | None) -> str | None:
    if field is None or not field.data:
        return None
    try:
        text = field.data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text:
        return None
    if any((ord(ch) < 32 and ch not in "\t\r\n") or ord(ch) == 127 for ch in text):
        return None
    return text


def positive_int(field: ProtoField | None) -> int:
    if field is None or field.value is None:
        return 0
    return field.value if field.value > 0 else 0


def decode_packed_varints(data: bytes) -> list[int]:
    values: list[int] = []
    offset = 0
    while offset < len(data):
        item = read_varint(data, offset)
        if item is None:
            break
        value, offset = item
        values.append(value)
    return values


def timestamp_to_iso(field: ProtoField | None) -> str | None:
    if field is None:
        return None

    text = field_text(field)
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            pass

    if field.data:
        nested = parse_fields(field.data)
        seconds = first(nested, 1)
        if seconds is not None and seconds.value is not None:
            nanos = first(nested, 2)
            nanos_value = nanos.value if nanos is not None and nanos.value is not None else 0
            try:
                ts = seconds.value + nanos_value / 1_000_000_000
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            except (OverflowError, OSError, ValueError):
                pass

    if field.value is not None:
        raw = field.value
        seconds = raw / 1000 if raw >= 1_000_000_000_000 else raw
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return None
    return None
