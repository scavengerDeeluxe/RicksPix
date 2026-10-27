"""Regression tests for the one-pass analyzer; no Ollama connection required."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from catalog_new_photos import exif_data, normalize_analysis


def example(category="Wildlife", description="A wild lynx in the forest"):
    return {
        "title": "North Shore Encounter",
        "description": description,
        "primary_category": category,
        "subcategory": "Animals",
        "season": "Winter",
        "quality": {"overall": 7, "sharpness": 7, "exposure": 7, "composition": 8},
        "publication": {
            "decision": "public", "confidence": 0.98,
            "contains_people": False, "private_context": False,
            "possible_rick_portrait": False,
        }
    }


class PhotoAnalyzerTests(unittest.TestCase):
    def test_wildlife_stays_wildlife(self):
        analysis, decision = normalize_analysis(example(), "local-test")
        self.assertEqual(analysis["primary_category"], "Wildlife")
        self.assertEqual(analysis["quality"]["overall"], 7)
        self.assertEqual(decision["decision"], "public")

    def test_dachshunds_not_wildlife(self):
        analysis, _ = normalize_analysis(
            example(description="Rick's dachshund resting on the snow"), "local-test")
        self.assertEqual(analysis["primary_category"], "Dachshunds")

    def test_pet_dog_not_wildlife(self):
        analysis, _ = normalize_analysis(
            example(description="A pet dog in a sunny yard"), "local-test")
        self.assertEqual(analysis["primary_category"], "Pets")

    @patch("catalog_new_photos.subprocess.run")
    def test_exif_non_cp1252_utf8(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=b'[{"EXIF:UserComment":"Snowy lynx \x81","IFD0:Make":"SONY"}]',
            stderr=b"")
        data = exif_data(Path("sample.jpg"))
        self.assertEqual(data["IFD0:Make"], "SONY")
        self.assertIn("Snowy lynx", data["EXIF:UserComment"])

    @patch("catalog_new_photos.subprocess.run")
    def test_malformed_exif_is_nonfatal(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"NOT JSON", stderr=b"")
        self.assertEqual(exif_data(Path("bad.jpg")), {})


if __name__ == "__main__":
    unittest.main()
