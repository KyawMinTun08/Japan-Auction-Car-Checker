from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_ACTIVITY = ROOT / "android-app/app/src/main/java/com/kyawmintun/jacc/MainActivity.kt"
GRADLE = ROOT / "android-app/app/build.gradle.kts"


def test_android_webview_supports_image_file_chooser() -> None:
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    assert "override fun onShowFileChooser" in source
    assert "ActivityResultContracts.OpenMultipleDocuments()" in source
    assert "fileChooserLauncher.launch(acceptedTypes)" in source
    assert "allowContentAccess = true" in source
    assert "filePathCallback?.onReceiveValue(null)" in source


def test_android_release_version_is_bumped_for_file_chooser_fix() -> None:
    source = GRADLE.read_text(encoding="utf-8")
    assert "versionCode = 103" in source
    assert 'versionName = "1.03"' in source
