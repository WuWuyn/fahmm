"""AT-09: missing facts remain unknown and source references stay reviewable."""

from test_cloud_minutes import make_cloud_service

from fahmm.offline_minutes import OfflineMinutesService
from fahmm.transcripts import TranscriptStore


def test_at09_no_invented_owner_deadline_and_cited_unverified_decision(tmp_path):
    service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
    TranscriptStore(service.meetings).save_edits(
        meeting_id, run_id,
        {2: "Chúng ta thống nhất thử nghiệm giao diện. Cần làm bản nháp."},
    )
    offline_id = OfflineMinutesService(service.meetings).generate(meeting_id)
    offline = service.minutes.read_version(meeting_id, offline_id)
    assert offline["content"]["actions"][0]["owner"] == "Chưa rõ"
    assert offline["content"]["actions"][0]["due_date"] == "Chưa rõ"
    assert offline["content"]["decisions"][0]["sources"][0]["segment_id"] == 2
    assert offline["manifest"]["review_state"] == "unverified"

    service._transport = lambda *_args: {
        "decisions": [{"text": "Thử nghiệm giao diện", "source_ids": [2]},
                      {"text": "Unrelated claim", "source_ids": [999]}],
        "actions": [{"task": "Làm bản nháp", "owner": "Invented person",
                     "due_date": "next Monday", "source_ids": [2]}],
    }
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    cloud_id = service.generate(snapshot, service.confirm(snapshot, True))
    cloud = service.minutes.read_version(meeting_id, cloud_id)
    action = cloud["content"]["actions"][0]
    assert action["owner"] == action["due_date"] == "Chưa rõ"
    assert action["needs_review"]
    cited = cloud["content"]["decisions"][0]
    assert cited["sources"] == [{"run_id": run_id, "segment_id": 2,
                                 "start": 0.0, "end": 2.0}]
    assert cited["needs_review"]
    invalid = cloud["content"]["decisions"][1]
    assert invalid["sources"] == [] and invalid["needs_review"]
    assert cloud["manifest"]["review_state"] == "unverified"
