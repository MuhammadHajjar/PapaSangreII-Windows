"""The GitHub updater: versions, what a release offers, and one real update
through the same PowerShell hand-off the game starts (tools/verify_updater.py
runs that and three harder cases)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from papasangre2.update import updater, version            # noqa: E402


def test_versions_are_dates_and_compare_as_dates():
    assert version.parse('2026-09-26 number 3') == (2026, 9, 26, 3)
    assert version.parse('2026-09-26-3') == (2026, 9, 26, 3)
    assert version.tag('2026-09-26 number 3') == '2026-09-26-3'
    assert version.tag('2026-09-27') == '2026-09-27'
    assert version.text('2026-09-26-3') == '2026-09-26 number 3'
    assert version.is_newer('2026-09-26-3', '2026-09-26 number 2')
    assert version.is_newer('2026-09-26-2', '2026-09-26')           # the day's first had no number
    assert version.is_newer('2026-10-01', '2026-09-30 number 4')
    assert not version.is_newer('2026-09-26-3', '2026-09-26 number 3')
    assert not version.is_newer('2026-09-26 number 2', '2026-09-26 number 3')
    assert not version.is_newer('latest', '2026-09-26')             # unknown is never offered
    assert version.current() and version.tag() == version.tag(version.current())


def test_the_zip_has_one_name_so_one_link_always_downloads_the_newest():
    r = updater.Release({'tag_name': '2026-09-27', 'assets': [
        {'name': 'Papa Sangre II manual.pdf', 'browser_download_url': 'x'},
        {'name': 'PapaSangreII-Windows.zip', 'browser_download_url': 'u', 'size': 7}]})
    assert r.asset_url == 'u'
    assert updater.LATEST_DOWNLOAD == ('https://github.com/MuhammadHajjar/PapaSangreII-Windows'
                                       '/releases/latest/download/PapaSangreII-Windows.zip')


def test_a_release_offers_its_own_zip_and_its_changes():
    r = updater.Release({
        'tag_name': '2026-09-27', 'body': 'Fixed a thing.\nAdded a thing.\n\nThe keys: A and D.',
        'assets': [{'name': 'Papa Sangre II manual.pdf', 'browser_download_url': 'x', 'size': 1},
                   {'name': 'PapaSangreII-Windows-2026-09-27.zip', 'browser_download_url': 'u',
                    'size': 5}]})
    assert r.asset_url == 'u' and r.asset_size == 5
    assert r.changes() == 'Fixed a thing.\nAdded a thing.'
    assert updater.Release({'tag_name': 't', 'assets': [
        {'name': 'a.zip', 'browser_download_url': 'a'}, {'name': 'b.zip', 'browser_download_url': 'b'},
    ]}).asset_url == ''                          # two strange zips: take neither


def test_an_update_never_writes_the_players_files_or_outside_the_folder():
    assert updater._safe('Play Papa Sangre II.exe')
    assert updater._safe('_internal/python312.dll')
    assert not updater._safe('config/progress.json')
    assert not updater._safe('Config/settings.json')
    assert not updater._safe('../outside.txt')
    assert not updater._safe('C:/Windows/evil.dll')
    assert not updater._safe('/etc/passwd')


def test_the_source_version_does_not_update_itself():
    ok, why = updater.can_update()
    assert not ok and 'source' in why


def test_a_real_update_goes_in_after_the_game_quits():
    if os.name != 'nt':
        return
    import verify_updater as v
    v.failures.clear()
    try:
        v.run_scenario('pytest: a normal update')
    finally:
        import shutil
        shutil.rmtree(v.WORK, ignore_errors=True)
    assert not v.failures, v.failures
