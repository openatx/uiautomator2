# coding: utf-8
#

import time

import pytest

import uiautomator2 as u2


@pytest.mark.skip("deprecated")
def test_screenrecord(d: u2.Device):
    import imageio
    with pytest.raises(RuntimeError):
        d.screenrecord.stop()

    d.screenrecord("output.mp4", fps=10)
    start = time.time()

    with pytest.raises(RuntimeError):
        d.screenrecord("output2.mp4")

    time.sleep(3.0)
    d.screenrecord.stop()
    print("Time used:", time.time() - start)

    # check
    with imageio.get_reader("output.mp4") as f:
        meta = f.get_meta_data()
        assert isinstance(meta, dict)
        from pprint import pprint
        pprint(meta)