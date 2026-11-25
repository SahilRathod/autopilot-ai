# V0.7 local production operator

Use Content planner to choose a channel, topic, format and optional registered footage. Set a local date/time or leave blank for immediate preparation. The persistent render worker processes due tasks when idle.

The operator creates an offline editable content template, not factual research. If footage is selected, it reuses existing candidates, scans only when none exist, ranks visual/audio cues and proposes up to three non-overlapping clips. Review actual footage and facts. Inspect/edit the script in the planner or AI Director. Approve the job in Approval center, then queue a suggested montage or use Media Studio. No automatic uploads.

Pending tasks can be cancelled. Failed/interrupted tasks require explicit retry. Each completed preparation links the draft and job atomically. If footage is rescanned, stored candidate IDs may become stale. The laptop and worker must stay running to process due tasks; closing the dashboard does not remove saved tasks. Date/time is stored in UTC and displayed locally. This is not a YouTube publication schedule.
