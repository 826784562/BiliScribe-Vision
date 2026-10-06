#!/usr/bin/env python3
"""Offline regression checks with real media; no model/API/network downloads."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

import bili_fetch
import evidence
import materials
import mock_asr
import transcribe
import video_visual
from common import digest, identity, read_json, save_transcript, seconds, write_json
from validate_course import validate


def make_fixture(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    unit = {'lesson_id': 'L001', 'bvid': 'BV1234567890', 'cid': 123, 'page': 1, 'title': 'Export demonstration',
            'duration': 12, 'source_order': 1, 'study_order': 1, 'selection': 'confirmed', 'added_by': 'user'}
    course = root / 'course'
    course.mkdir(exist_ok=True)
    write_json(course / 'course_manifest.json', {'schema_version': 1, 'course_id': 'offline-export-demo', 'units': [unit]})
    transcript = [
        {'start': 0, 'end': 4, 'text': '打开工具菜单，选择导出。', 'timing': 'segment'},
        {'start': 4, 'end': 8, 'text': '这里设置CSV格式，分隔符选逗号，文件名照图上填，然后点击导出。', 'timing': 'segment'},
        {'start': 8, 'end': 12, 'text': '导出完成后检查文件名以及行列数。', 'timing': 'segment'},
    ]
    save_transcript(bili_fetch.stable_stem(unit), transcript, root / 'transcripts', unit, 'synthetic-test-transcript')
    video = root / 'demo.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (960, 540))
    if not writer.isOpened():
        raise RuntimeError('fixture video writer unavailable')
    pages = [
        ['DATA LAB | Tools menu', 'Export...', 'Dataset: 12 rows, 3 columns'],
        ['EXPORT SETTINGS', 'Format: CSV', 'Delimiter: comma (,)', 'Filename: lesson.csv', '[ EXPORT ]'],
        ['EXPORT COMPLETE', 'Saved: lesson.csv', 'Rows: 12', 'Columns: 3', '[ OK ]'],
    ]
    for i in range(120):
        index = i // 40
        frame = np.full((540, 960, 3), [(45, 35, 25), (245, 245, 245), (65, 115, 45)][index], dtype=np.uint8)
        color = (0, 0, 0) if index == 1 else (255, 255, 255)
        for line, text in enumerate(pages[index]):
            cv2.putText(frame, text, (50, 90 + line * 85), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2, cv2.LINE_AA)
        writer.write(frame)
    writer.release()
    return {'root': root, 'course': course, 'unit': unit, 'video': video}


def prepared_fixture(root: Path) -> tuple[dict, dict]:
    fixture = make_fixture(root)
    states = video_visual.candidate_segments(fixture['video'], 'L001', 1, root / 'frames')
    selected = video_visual.select_frames(states)
    visual = root / 'visual_manifest.json'
    write_json(visual, {'schema_version': 2, 'segments': selected})
    result = evidence.prepare(fixture['course'] / 'course_manifest.json', root / 'transcripts', 'transcript-images',
                              root / 'evidence_manifest.json', [visual])
    return fixture, result


def analysis_for(packet: dict) -> dict:
    # Test content deliberately does not assert a real model read or semantic correctness.
    row = packet['transcript'][0]
    return {'packet_id': packet['packet_id'], 'mode': packet['mode'], 'status': 'complete',
            'summary': 'Offline record format fixture; no real model understanding claimed.',
            'reviewed_frame_ids': [f['frame_id'] for f in packet['frames']],
            'entries': [{'entry_id': packet['packet_id'] + '-E1', 'kind': 'concept', 'text': row['text'],
                         'provenance': 'COURSE_SPOKEN', 'timestamp': max(row['start'], packet['start']),
                         'transcript_ids': [row['id']], 'frame_ids': [], 'quote': row['text']}],
            'operations': [], 'contradictions': [], 'gaps': []}


class PipelineChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='biliscribe-check-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_real_video_has_three_states(self):
        fixture, prepared = prepared_fixture(self.root)
        self.assertEqual(len(prepared['packets']), 3)
        self.assertEqual([(p['start'], p['end']) for p in prepared['packets']], [(0, 4), (4, 8), (8, 12)])
        self.assertTrue(all(len(p['frames']) <= 2 for p in prepared['packets']))
        self.assertTrue(all(Path(p['context_path']).exists() for p in prepared['packets']))

    def test_explicit_action_windows_and_completed_frame(self):
        fixture = make_fixture(self.root)
        windows = [{'start': 0, 'end': 4}, {'start': 4, 'end': 6}, {'start': 6, 'end': 8}, {'start': 8, 'end': 12}]
        states = video_visual.candidate_segments(fixture['video'], 'L001', 2, self.root / '步骤图片', windows)
        self.assertEqual(len(states), 4)
        selected = video_visual.select_frames([{'lesson_id': 'L001', 'segment_id': 'S1', 'start': 0, 'end': 10,
            'candidates': [{'timestamp': 5, 'stable': True, 'completed': True, 'completeness': 1},
                           {'timestamp': 9, 'stable': True, 'completed': False, 'completeness': .4}]}], 'final')
        self.assertEqual(selected[0]['selected_frames'][0]['timestamp'], 5)

    def test_erasure_preserves_earlier_information(self):
        segment = {'lesson_id': 'L001', 'segment_id': 'S1', 'start': 0, 'end': 10, 'candidates': [
            {'timestamp': 2, 'stable': True, 'completeness': .8}, {'timestamp': 8, 'stable': True, 'completeness': .2}]}
        frames = video_visual.select_frames([segment])[0]['selected_frames']
        self.assertEqual([f['role'] for f in frames], ['pre_erase_backup', 'completed_state'])

    def test_no_fake_image_read_and_operation_gaps(self):
        _, prepared = prepared_fixture(self.root)
        packet = prepared['packets'][0]
        analysis = analysis_for(packet)
        analysis['reviewed_frame_ids'] = []
        with self.assertRaises(ValueError):
            evidence.check_analysis(packet, analysis)
        analysis = analysis_for(packet)
        analysis['entries'][0]['kind'] = 'operation'
        with self.assertRaises(ValueError):
            evidence.check_analysis(packet, analysis)
        analysis = analysis_for(packet)
        analysis['operations'] = [{'title': 'Export', 'prerequisites': [], 'reproducible': True,
                                  'missing': ['filename unknown'], 'steps': []}]
        with self.assertRaises(ValueError):
            evidence.check_analysis(packet, analysis)

    def test_text_only_never_reads_visual_input(self):
        fixture = make_fixture(self.root)
        prepared = evidence.prepare(fixture['course'] / 'course_manifest.json', self.root / 'transcripts', 'transcript-only',
                                    self.root / 'text-evidence.json', [self.root / 'DOES-NOT-EXIST.json'])
        self.assertTrue(all(not p['frames'] for p in prepared['packets']))
        analysis = analysis_for(prepared['packets'][0])
        analysis['entries'][0]['provenance'] = 'COURSE_VISUAL'
        with self.assertRaises(ValueError):
            evidence.check_analysis(prepared['packets'][0], analysis)

    def test_record_coverage_and_changed_inputs(self):
        fixture, prepared = prepared_fixture(self.root)
        output = fixture['course'] / 'understanding_manifest.json'
        for packet in prepared['packets']:
            path = self.root / 'analysis.json'
            write_json(path, analysis_for(packet))
            evidence.record(self.root / 'evidence_manifest.json', path, output, 'offline-format-fixture')
        self.assertEqual(evidence.coverage(prepared, read_json(output)), [])
        changed = copy.deepcopy(prepared)
        changed['packets'][0]['input_fingerprint'] = 'different'
        self.assertTrue(evidence.coverage(changed, read_json(output)))
        frame = Path(prepared['packets'][0]['frames'][0]['frame_path'])
        frame.write_bytes(b'changed')
        write_json(self.root / 'analysis.json', analysis_for(prepared['packets'][0]))
        with self.assertRaises(ValueError):
            evidence.record(self.root / 'evidence_manifest.json', self.root / 'analysis.json', output)

    def test_missing_deliverables_and_wrong_lesson_do_not_pass(self):
        fixture, prepared = prepared_fixture(self.root)
        notes = fixture['course'] / '讲义'
        notes.mkdir()
        (notes / 'L001.md').write_text('# L001\n', encoding='utf-8')
        errors, _, _ = validate(fixture['course'])
        self.assertTrue(any('empty lesson' in e for e in errors))
        self.assertTrue(any('deliverable' in e for e in errors))
        self.assertTrue(any('understanding' in e for e in errors))
        with self.assertRaises(ValueError):
            seconds('00:99')

    def test_import_timed_transcript_preserves_identity(self):
        fixture = make_fixture(self.root)
        srt = self.root / 'lesson.srt'
        srt.write_text('1\n00:00:00,100 --> 00:00:02,500\n测试字幕。\n', encoding='utf-8')
        out = self.root / 'imported'
        evidence.import_transcript(fixture['course'] / 'course_manifest.json', 'L001', srt, out)
        imported = read_json(next(out.glob('*.json')))
        self.assertEqual(imported['identity'], identity(fixture['unit']))
        self.assertEqual(imported['segments'][0]['end'], 2.5)
        plain = self.root / 'whole-lesson.txt'
        plain.write_text('已有转录没有时间，但不能伪造按钮点击时间。', encoding='utf-8')
        evidence.import_transcript(fixture['course'] / 'course_manifest.json', 'L001', plain, out)
        imported = read_json(next(out.glob('*.json')))
        self.assertEqual(imported['segments'][0]['timing'], 'coarse')
        self.assertEqual((imported['segments'][0]['start'], imported['segments'][0]['end']), (0, 12))

    def test_stale_transcript_and_duplicate_understanding_are_rejected(self):
        fixture, prepared = prepared_fixture(self.root)
        output = fixture['course'] / 'understanding_manifest.json'
        for packet in prepared['packets']:
            write_json(self.root / 'analysis.json', analysis_for(packet))
            evidence.record(self.root / 'evidence_manifest.json', self.root / 'analysis.json', output)
        understanding = read_json(output)
        understanding['records'].append(understanding['records'][0])
        self.assertIn('duplicate understanding packet ID', evidence.coverage(prepared, understanding))
        source = Path(prepared['transcript_sources'][0]['path'])
        source.write_text(source.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed source transcript'):
            evidence.record(self.root / 'evidence_manifest.json', self.root / 'analysis.json', output)

    def test_course_validation_checks_real_heading_and_selected_book_range(self):
        fixture, prepared = prepared_fixture(self.root)
        course = fixture['course']
        for packet in prepared['packets']:
            write_json(self.root / 'analysis.json', analysis_for(packet))
            evidence.record(self.root / 'evidence_manifest.json', self.root / 'analysis.json', course / 'understanding_manifest.json')
        for name in ('大纲.md', '术语表.md', '习题讲解.md'):
            (course / name).write_text('完整检查用文字。', encoding='utf-8')
        (course / '交付报告.md').write_text('transcript-images；未直接听取原始音频；语义抽查未执行，只有离线格式检查。', encoding='utf-8')
        notes = course / '讲义'
        notes.mkdir()
        note = notes / 'L001.md'
        note.write_text('# L001 · 检查\n\n打开工具菜单。（L001-VS0001-E1）\n', encoding='utf-8')
        self.assertEqual(validate(course)[0], [])
        note.write_text('# L002 · 检查\n\n打开工具菜单。（L001-VS0001-E1）\n', encoding='utf-8')
        self.assertTrue(any('unknown/missing lesson' in e for e in validate(course)[0]))
        note.write_text('# L001 · 检查\n\n打开工具菜单。（L001-VS0001-E1）\n[课本补充] C001 课本 P2（PDF 第 2 页）。\n', encoding='utf-8')
        write_json(course / 'textbook_manifest.json', {'chapters': [{'id': 'C001', 'selected': True, 'pdf_start': 1,
                   'pdf_end': 1, 'page_status': 'confirmed'}], 'book_page_map': {'1': '1', '2': '2'}})
        (course / '互补大纲.md').write_text('C001 补充定义。', encoding='utf-8')
        self.assertTrue(any('outside selected chapter' in e for e in validate(course)[0]))

    def test_collection_pagination_keeps_all_video_parts(self):
        first = [{'bvid': f'BV{i:010d}'} for i in range(100)]
        with patch.object(bili_fetch, 'api', side_effect=[{'archives': first, 'page': {'total': 101}},
                           {'archives': [{'bvid': 'BV0000000100'}], 'page': {'total': 101}}]), \
             patch.object(bili_fetch.time, 'sleep'):
            kind, records = bili_fetch.archive_records('https://space.bilibili.com/123/lists/456?type=season')
        self.assertEqual((kind, len(records)), ('collection', 101))
        def parts(bv, cookie):
            cid = int(bv[2:]) * 10 + 1
            return bv, [{'page': 1, 'cid': cid, 'part': 'part 1', 'duration': 4},
                        {'page': 2, 'cid': cid + 1, 'part': 'part 2', 'duration': 4}]
        with patch.object(bili_fetch, 'fetch_video', side_effect=parts), patch.object(bili_fetch.time, 'sleep'):
            manifest = bili_fetch.manifest_from_records(records, 'Complete course', kind)
        self.assertEqual(len(manifest['units']), 202)
        self.assertEqual(manifest['units'][-1]['page'], 2)

    def test_glossary_updates_structured_transcript_as_well_as_text(self):
        make_fixture(self.root)
        terms = self.root / 'terms.json'
        write_json(terms, {'逗号': '半角逗号'})
        args = SimpleNamespace(apply_glossary=str(terms), glossary_min_len=2,
                               inputs=[str(self.root / 'transcripts')], outdir=str(self.root / 'transcripts'), dry_run=False)
        self.assertEqual(transcribe.run_glossary(args), 0)
        transcript = read_json(next((self.root / 'transcripts').glob('*.json')))
        self.assertIn('半角逗号', transcript['segments'][1]['text'])

    def test_subtitles_use_manifest_identity(self):
        fixture = make_fixture(self.root)
        args = SimpleNamespace(input=str(fixture['course'] / 'course_manifest.json'), outdir=str(self.root / 'subs'), cookie=None, delay=0)
        with patch.object(bili_fetch, 'api', return_value={'subtitle': {'subtitles': [{'lan': 'zh', 'subtitle_url': 'https://fixture.invalid/subs'}]}}), \
             patch.object(bili_fetch, '_get', return_value=json.dumps({'body': [{'from': 0, 'to': 3, 'content': '字幕测试'}]}).encode()):
            self.assertEqual(bili_fetch.cmd_subs(args), 0)
        data = read_json(next((self.root / 'subs').glob('*.json')))
        self.assertEqual(data['identity'], identity(fixture['unit']))

    def test_legacy_combined_video_is_extracted_to_real_audio(self):
        fixture = make_fixture(self.root)
        audio = self.root / 'tone.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(b'\x00\x00' * 16000)
        combined = self.root / 'combined.mp4'
        ffmpeg = bili_fetch.ffmpeg_executable()
        subprocess.run([ffmpeg, '-v', 'error', '-i', str(fixture['video']), '-i', str(audio),
                        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-y', str(combined)], check=True)
        args = SimpleNamespace(input=str(fixture['course'] / 'course_manifest.json'), outdir=str(self.root / 'downloads'),
                               cookie=None, delay=0, force=False, allow_weak_verify=False)
        def local_download(urls, target, cookie, **kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(combined, target)
        with patch.object(bili_fetch, 'api', return_value={'durl': [{'url': 'https://fixture.invalid/video'}]}), \
             patch.object(bili_fetch, 'download', side_effect=local_download):
            self.assertEqual(bili_fetch.cmd_audio(args), 0)
        target = next((self.root / 'downloads').glob('*.m4a'))
        self.assertEqual(bili_fetch.decode_errors(target), 0)
        self.assertFalse(list((self.root / 'downloads').glob('*.legacy.mp4')))
        self.assertNotIn(b'vide', target.read_bytes())

    def test_cloud_upload_and_timed_outputs(self):
        audio = self.root / 'short.wav'
        with wave.open(str(audio), 'wb') as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(b'\x00\x00' * 16000)
        server = ThreadingHTTPServer(('127.0.0.1', 0), mock_asr.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            rows = list(transcribe.cloud_segments(audio, self.root / 'segments', f'http://127.0.0.1:{server.server_port}/v1', 'mock', 'dummy', 'zh'))
            self.assertEqual(len(rows), 1)
            self.assertGreater(rows[0]['end'], 0)
            self.assertEqual(rows[0]['timing'], 'coarse')
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=2)
        self.assertEqual(bili_fetch.decode_errors(audio), 0)

    def test_material_images_pdf_pages_and_chapter_mapping(self):
        import pymupdf as fitz
        pdf = self.root / 'book.pdf'
        document = fitz.open()
        for i in range(2):
            page = document.new_page()
            page.insert_text((30, 50), f'Chapter {i + 1} Export settings and comma-separated values are explained on this page.')
        document.set_toc([[1, 'Chapter 1 Export', 1], [1, 'Chapter 2 Validation', 2]])
        document.save(pdf); document.close()
        rendered = materials.render_pdf_pages(pdf, '1-2', self.root / 'pdf-images')
        self.assertEqual(len(rendered['pages']), 2)
        selected_text, selected_count, _ = materials.text_from_pdf(pdf, '2')
        self.assertEqual(selected_count, 1)
        self.assertEqual(selected_text[0][0], '第2页')
        self.assertNotIn('Chapter 1', selected_text[0][1])
        chapters, method = materials.textbook_chapters(pdf)
        self.assertEqual(method, 'outline')
        self.assertEqual([(c['pdf_start'], c['pdf_end']) for c in chapters], [(1, 1), (2, 2)])
        args = SimpleNamespace(pdf=str(pdf), select='1', output=str(self.root / 'textbook.json'), book_page_offset=0, confirm_page_labels=False)
        self.assertEqual(materials.cmd_textbook(args), 0)
        textbook = read_json(self.root / 'textbook.json')
        self.assertEqual(textbook['book_page_map']['1'], '1')
        ppt = self.root / 'slides.pptx'
        image = cv2.imencode('.png', np.full((20, 20, 3), 200, dtype=np.uint8))[1].tobytes()
        with zipfile.ZipFile(ppt, 'w') as z:
            z.writestr('ppt/slides/slide1.xml', '<a:t xmlns:a="a">CSV &amp; separator</a:t>')
            z.writestr('ppt/slides/slide2.xml', '<a:t xmlns:a="a">First in presentation</a:t>')
            z.writestr('ppt/presentation.xml', '<p:sldIdLst xmlns:p="p" xmlns:r="r"><p:sldId id="2" r:id="r2"/><p:sldId id="1" r:id="r1"/></p:sldIdLst>')
            z.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="slides/slide2.xml"/></Relationships>')
            z.writestr('ppt/slides/_rels/slide1.xml.rels', '<Relationships><Relationship Type="x/image" Target="../media/image1.png"/></Relationships>')
            z.writestr('ppt/media/image1.png', image)
        self.assertEqual(materials.text_from_pptx(ppt)[0][1], 'First in presentation')
        self.assertIn('&', materials.text_from_pptx(ppt)[1][1])
        extracted = materials.extract_pptx_images(ppt, self.root / 'ppt-images')
        self.assertEqual(extracted[0]['slide'], 2)
        self.assertTrue(Path(extracted[0]['image_path']).exists())
        with zipfile.ZipFile(ppt, 'w') as z:
            z.writestr('ppt/slides/slide1.xml', '<slide/>')
            z.writestr('ppt/slides/_rels/slide1.xml.rels', '<Relationships><Relationship Type="x/image" Target="../media/image1.png"/></Relationships>')
            z.writestr('ppt/media/image1.png', image)
        out = self.root / 'image-only-notes'
        with patch.object(sys, 'argv', ['materials.py', str(ppt), '--extract-images', '-o', str(out), '--image-dir', str(self.root / 'image-only')]):
            self.assertEqual(materials.main(), 0)
        self.assertTrue(read_json(out / '_manifest.json')['sources'][0]['images'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--demo':
        fixture, prepared = prepared_fixture(Path(sys.argv[2]).resolve())
        print(json.dumps({'course': str(fixture['course']), 'evidence': str(fixture['root'] / 'evidence_manifest.json'),
                          'packets': [p['context_path'] for p in prepared['packets']]}, ensure_ascii=False, indent=2))
    else:
        unittest.main()
