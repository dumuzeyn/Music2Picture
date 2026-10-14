from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DocumentationTests(unittest.TestCase):
    def test_readme_contains_both_engines_and_diagrams_in_both_languages(self):
        text = (ROOT/'README.md').read_text(encoding='utf-8')
        self.assertEqual(text.count('```mermaid'), 4)
        self.assertIn('M2Pv1', text)
        self.assertIn('M2Pv2', text)
        self.assertIn('M2Pv3', text)
        russian, english = text.split('\n## English\n',1)
        self.assertTrue(russian.rstrip().endswith('---'))
        self.assertIn('Автор проекта:', russian.split('## Ограничения')[-1])
        self.assertIn('Project author:', english.split('### Limits')[-1])
        self.assertIn('FFmpeg не включён', russian)
        self.assertIn('FFmpeg is not bundled', english)

    def test_every_relative_readme_link_exists(self):
        text = (ROOT/'README.md').read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if target.startswith(('http','https','#')):
                continue
            with self.subTest(target=target):
                self.assertTrue((ROOT/target).exists())

    def test_no_personal_music_or_build_artifacts_are_used_in_docs(self):
        text = (ROOT/'README.md').read_text(encoding='utf-8')
        self.assertNotIn('C:/Users/',text)
        self.assertNotIn('C:\\Users\\',text)
        self.assertNotIn('КРУЖИТ',text)
        self.assertNotIn('Baby One More Time',text)


if __name__ == '__main__':
    unittest.main()
