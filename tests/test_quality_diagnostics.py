import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from scripts import quality_diagnostics as diagnostics
from scripts.quality_suite import decoder_preflight
from scripts.prepare_quality_benchmark import METRIC, METRIC_REVISION
from scripts.prepare_quality_benchmark import prepare
from src.experiments import ExperimentConfig
from src.lineage import sha256_file, canonical_hash


def test_controls_have_no_self_pairs_in_negative_group_and_fixed_order():
    ids = [str(i) for i in range(10)]
    truth = {key: {"summary": "summary " + key} for key in ids}
    predictions = {"0": {"summary": "model prediction"}}
    pairs = diagnostics.control_pairs(list(reversed(ids)), truth, predictions)
    assert pairs == diagnostics.control_pairs(ids, truth, predictions)
    negatives = [p for p in pairs if p["kind"] == "mismatched"]
    assert len(negatives) == 8
    assert all(p["video_id"] != p["reference_video_id"] and p["candidate"] != p["reference"] for p in negatives)
    assert len([p for p in pairs if p["kind"] == "model"]) == 1


@pytest.mark.parametrize("ids,truth", [(["a"], {"a": {"summary": "one"}}),
    (["a", "b"], {"a": {"summary": "same"}, "b": {"summary": "same"}})])
def test_invalid_controls_are_rejected(ids, truth):
    with pytest.raises(ValueError, match="distinct"):
        diagnostics.control_pairs(ids, truth, {})


def test_failure_selected_configs_disable_acceptance_scoring(tmp_path):
    cfg = ExperimentConfig(name="baseline", model_name="test", model_revision="a" * 40,
                           video_ids=["a", "b", "c"])
    baseline = {"resolved_config": cfg.model_dump(mode="json"),
                "failures": [{"video_id": "a"}, {"video_id": "b"}],
                "predictions": [{"video_id": "c"}]}
    configs = diagnostics.diagnostic_configs(baseline, tmp_path / "configs")
    resolved = [ExperimentConfig.model_validate_json(path.read_text()) for path in configs]
    assert resolved[0].constrain_category and not resolved[1].constrain_category
    assert all(not cfg.evaluate_summary and cfg.summary_metric_snapshot is None for cfg in resolved)
    assert all(cfg.video_ids == ["a", "b", "c"] for cfg in resolved)
    assert cfg.evaluate_summary  # the baseline was not mutated


def test_constraint_cannot_be_silently_ignored_by_combined_strategy():
    with pytest.raises(ValidationError, match="two-pass"):
        ExperimentConfig(name="test", model_name="test", model_revision="a" * 40,
                         video_ids=["a"], strategy="per_video_combined", constrain_category=True)


def test_calibration_records_both_layer_identities_without_modifying_baseline(tmp_path, monkeypatch):
    truth_path = tmp_path / "truth.csv"
    with truth_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['video_id', 'summary', 'category'])
        writer.writeheader()
        writer.writerows([{'video_id': key, 'summary': 'reference '+key, 'category': 'News'} for key in ('a','b')])
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'ground_truth': {'path': 'truth.csv', 'bytes': truth_path.stat().st_size,
        'sha256': sha256_file(truth_path)}, 'records': []}), encoding='utf-8')
    cfg = ExperimentConfig(name='test', model_name='test', model_revision='a'*40, video_ids=['a','b'],
                           manifest=manifest, dataset_root=tmp_path)
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'resolved_config': cfg.model_dump(mode='json'),
        'lineage': {'manifest_hash': sha256_file(manifest)},
        'predictions': [{'video_id': 'a', 'summary': 'model text'}]}), encoding='utf-8')
    original = baseline.read_bytes()
    snapshot = tmp_path / ('models--'+METRIC.replace('/', '--')) / 'snapshots' / METRIC_REVISION
    snapshot.mkdir(parents=True)
    monkeypatch.setenv('HF_HUB_CACHE', str(tmp_path))
    constructed = []
    class FakeScorer:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
        def score(self, candidates, references):
            return None, None, SimpleNamespace(tolist=lambda: [1.0 if c == r else .2 for c,r in zip(candidates,references)])
    monkeypatch.setitem(sys.modules, 'bert_score', SimpleNamespace(BERTScorer=FakeScorer))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(AutoConfig=SimpleNamespace(
        from_pretrained=lambda *a, **k: SimpleNamespace(num_hidden_layers=24, model_type='xlm-roberta'))))
    monkeypatch.setattr(diagnostics, 'version', lambda name: 'test')
    output = tmp_path / 'controls.json'
    diagnostics.calibration(baseline, output)
    result = json.loads(output.read_text())
    assert [c['num_layers'] for c in constructed] == [24,17]
    assert all(c['device'] == 'cpu' and c['batch_size'] == 1 for c in constructed)
    assert len({item['metric_hash'] for item in result['layers']}) == 2
    assert all(item['self_minus_mismatched'] == .8 for item in result['layers'])
    assert baseline.read_bytes() == original


@pytest.mark.parametrize("backend", ["torchcodec", "torchvision"])
def test_decoder_preflight_checks_frame_cap_and_refuses_fallback(tmp_path, monkeypatch, backend):
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'records': [{'video_id': 'a', 'video': {'path': 'a.mp4'}}]}))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'manifest': str(manifest), 'dataset_root': str(tmp_path),
        'video_ids': ['a'], 'model_name': 'test', 'model_revision': 'a'*40, 'max_frames': 4}))
    metadata = SimpleNamespace(video_backend=backend)
    class Frames:
        def __len__(self): return 4
        def numel(self): return 4*640*480*3
        def element_size(self): return 1
    class Processor:
        def sample_frames(self, metadata, num_frames):
            assert self.do_sample_frames and self.num_frames == num_frames == 4
            return [0,25,50,75]
        def fetch_videos(self, path, sample_indices_fn):
            assert sample_indices_fn(metadata=metadata) == [0,25,50,75]
            return Frames(), metadata
    monkeypatch.setitem(sys.modules, 'torchcodec', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'torchcodec.decoders', SimpleNamespace(VideoDecoder=object))
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(AutoProcessor=SimpleNamespace(
        from_pretrained=lambda *a, **k: SimpleNamespace(video_processor=Processor()))))
    monkeypatch.setattr('scripts.quality_suite.subprocess.check_output', lambda *a, **k:
        json.dumps({'streams': [{'width': 640, 'height': 480, 'nb_frames': '100'}]}).encode())
    if backend == 'torchcodec':
        result = decoder_preflight(config)
        assert result['sampled_frames'] == 4 and result['full_rgb_bytes'] == 100*640*480*3
    else:
        with pytest.raises(RuntimeError, match='bounded TorchCodec'):
            decoder_preflight(config)


def test_scorer_controls_reused_only_for_same_baseline_and_both_layer_identities(tmp_path, monkeypatch):
    baseline = tmp_path / 'baseline.json'
    baseline.write_text('{}')
    cached = tmp_path / 'old' / 'scorer-controls.json'
    cached.parent.mkdir()
    report = {'baseline_sha256': sha256_file(baseline), 'layers': [
        {'metric': {'num_layers': layer, 'snapshot_revision': METRIC_REVISION,
                    'bert_score': '0.3.13', 'rescale_with_baseline': False}} for layer in (24,17)]}
    monkeypatch.setattr(diagnostics, 'version', lambda name: '0.3.13')
    cached.write_text(json.dumps(report))
    assert diagnostics.reusable_controls(baseline, tmp_path) == cached
    report['layers'].pop()
    cached.write_text(json.dumps(report))
    assert diagnostics.reusable_controls(baseline, tmp_path) is None
    report['layers'].append({'metric': {'num_layers': 17, 'snapshot_revision': METRIC_REVISION,
                                      'bert_score': 'different', 'rescale_with_baseline': False}})
    cached.write_text(json.dumps(report))
    assert diagnostics.reusable_controls(baseline, tmp_path) is None
    baseline.write_text('{"changed": true}')
    assert diagnostics.reusable_controls(baseline, tmp_path) is None


@pytest.mark.parametrize('constrained,expected_runs', [(False,3),(True,2)])
def test_comparison_variants_preserve_paired_inputs_and_scorer(tmp_path, monkeypatch, constrained, expected_runs):
    monkeypatch.chdir(tmp_path)
    manifest = Path('data/manifests/tiktok-video-v1.json')
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}')
    subset = tmp_path / 'subset.json'
    subset.write_text(json.dumps({'manifest_hash': sha256_file(manifest),
        'sample_hash': canonical_hash(['a','b']), 'records': [{'video_id':'b'},{'video_id':'a'}]}))
    paths = prepare(tmp_path / 'cache', tmp_path / 'configs', subset, download=False, constrained=constrained)
    configs = [ExperimentConfig.model_validate_json(path.read_text()) for path in paths]
    assert len(configs) == expected_runs
    assert all(c.video_ids == ['a','b'] and c.summary_metric_layers == 17 for c in configs)
    assert len({str(c.summary_metric_snapshot) for c in configs}) == 1
    assert all(c.constrain_category == constrained for c in configs)
    if constrained:
        assert [c.max_frames for c in configs] == [4,2]
        assert all(c.strategy == 'per_video_two_pass' for c in configs)
