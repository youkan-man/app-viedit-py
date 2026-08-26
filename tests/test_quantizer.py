from __future__ import annotations

import pytest

from app.errors import AppError
from app.quantizer import QuantizeOptions, quantize_xml


def test_quantizes_object_position_without_resizing() -> None:
    xml = '<RSRC><bounds>(3, 5, 103, 55)</bounds></RSRC>'
    result = quantize_xml(xml, QuantizeOptions(grid_size=8))

    assert '<bounds>(0, 8, 100, 58)</bounds>' in result['content']
    report = result['report']
    assert report['matched_by_kind']['object'] == 1
    assert report['changed_by_kind']['object'] == 1
    assert report['changed_values'] == 4


def test_optional_rectangle_size_quantization() -> None:
    xml = '<RSRC><bounds>(3, 5, 103, 55)</bounds></RSRC>'
    result = quantize_xml(
        xml,
        QuantizeOptions(grid_size=8, resize_rectangles=True),
    )

    # 100x50 becomes 104x48 after the top-left position is snapped.
    assert '<bounds>(0, 8, 104, 56)</bounds>' in result['content']


def test_connector_scope_does_not_move_regular_objects() -> None:
    xml = (
        '<RSRC><SL__object>'
        '<bounds>(3, 5, 103, 55)</bounds>'
        '<termBounds>(5, 9, 25, 19)</termBounds>'
        '<termHotPoint>(7, 11)</termHotPoint>'
        '</SL__object></RSRC>'
    )
    result = quantize_xml(
        xml,
        QuantizeOptions(
            grid_size=8,
            include_objects=False,
            include_connectors=True,
            include_wires=False,
        ),
    )

    assert '<bounds>(3, 5, 103, 55)</bounds>' in result['content']
    assert '<termBounds>(8, 8, 28, 18)</termBounds>' in result['content']
    assert '<termHotPoint>(8, 8)</termHotPoint>' in result['content']
    assert result['report']['changed_by_kind'] == {
        'object': 0,
        'connector': 2,
        'wire': 0,
    }


def test_wire_array_points_are_classified_by_ancestor() -> None:
    xml = (
        '<RSRC><wireTable>'
        '<SL__array><SL__arrayElement>(13, 19)</SL__arrayElement></SL__array>'
        '</wireTable></RSRC>'
    )
    result = quantize_xml(
        xml,
        QuantizeOptions(
            grid_size=8,
            include_objects=False,
            include_connectors=False,
            include_wires=True,
        ),
    )

    assert '(16, 16)' in result['content']
    assert result['report']['changed_by_kind']['wire'] == 1
    assert result['report']['warnings'] == []


def test_compressed_wire_table_is_reported_but_not_modified() -> None:
    xml = '<RSRC><compressedWireTable>DEADBEEF</compressedWireTable></RSRC>'
    result = quantize_xml(
        xml,
        QuantizeOptions(
            grid_size=8,
            include_objects=False,
            include_connectors=False,
            include_wires=True,
        ),
    )

    assert result['content'] == xml
    assert result['report']['changed_elements'] == 0
    assert any('バイナリ' in warning for warning in result['report']['warnings'])


def test_already_quantized_xml_is_returned_byte_for_byte() -> None:
    xml = "<?xml version='1.0'?>\n<RSRC>\n  <bounds>(8, 16, 24, 32)</bounds>\n</RSRC>\n"
    result = quantize_xml(xml, QuantizeOptions(grid_size=8))

    assert result['content'] == xml
    assert result['report']['changed_elements'] == 0


def test_hex_coordinate_notation_is_preserved() -> None:
    xml = '<RSRC><bounds>(0x3, 0X5, 0x13, 0X15)</bounds></RSRC>'
    result = quantize_xml(xml, QuantizeOptions(grid_size=8))

    assert '<bounds>(0x0, 0X8, 0x10, 0X18)</bounds>' in result['content']


def test_dtd_is_rejected() -> None:
    xml = '<!DOCTYPE RSRC [<!ENTITY x "boom">]><RSRC><bounds>&x;</bounds></RSRC>'
    with pytest.raises(AppError) as raised:
        quantize_xml(xml, QuantizeOptions())
    assert raised.value.code == 'invalid_xml'


def test_empty_scope_is_rejected() -> None:
    with pytest.raises(AppError) as raised:
        quantize_xml(
            '<RSRC />',
            QuantizeOptions(
                include_objects=False,
                include_connectors=False,
                include_wires=False,
            ),
        )
    assert raised.value.code == 'empty_quantize_scope'
