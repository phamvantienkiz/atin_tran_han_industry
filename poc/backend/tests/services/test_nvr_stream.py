from app.ai.nvr_stream import NvrStreamManager, extract_jpeg_frames


def test_extract_jpeg_frames_handles_single_multiple_and_split_chunks() -> None:
    jpg1 = b"\xff\xd8\x01\x02\x03\xff\xd9"
    jpg2 = b"\xff\xd8\xaa\xbb\xff\xd9"
    part_a = b"\xff\xd8\x11\x22"
    part_b = b"\x33\x44\xff\xd9"

    buf = bytearray(b"--myboundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpg1 + b"\r\n" + jpg2 + part_a)
    extracted = extract_jpeg_frames(buf)
    assert extracted == [jpg1, jpg2]
    # Unfinished third JPEG stays buffered
    assert bytes(buf) == part_a

    buf.extend(part_b)
    extracted2 = extract_jpeg_frames(buf)
    assert extracted2 == [part_a + part_b]
    assert len(buf) == 0


def test_nvr_stream_manager_unconfigured_is_noop() -> None:
    mgr = NvrStreamManager(
        nvr_base_url="http://127.0.0.1:80",
        nvr_user="",
        nvr_pass="",
        nvr_configured=False,
    )
    mgr.sync_cameras([{"id": "ch16", "channel": 16, "subtype": 0, "enabled": True}])
    assert mgr.active_camera_ids() == []
    assert mgr.latest("ch16") is None
    mgr.stop_all()
