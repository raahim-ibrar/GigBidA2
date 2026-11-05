# Data card - to complete after supplied assets are available

Expected sources: three synthetic freelancer persona corpora, historical/live GigSim jobs, client histories, outcome-labelled past proposals, instructor policy pack and labelled dev jobs.

Current state: these datasets have not been imported. Directory markers are not datasets. No hidden test set may enter this repository.

For each source record license/permission, source version/hash, counts, formats, dates, missing fields, duplicated projects and limitations. Every chunk needs persona, type, project, skills, date, client industry and proposal outcome when applicable. Preserve source item IDs for gold-evidence scoring.

Record train/development/experimental splits and fixed seeds. Deduplicate repeated descriptions without losing source provenance. Keep real client information and live-mode data private. Mask PII in logs and traces.

Proposed RAG comparison: V0 baseline plus V1 requirement decomposition, V2 hybrid fusion, V3 reranking and V8 corrective retrieval. Components need both isolated comparison and combination/ablation. Do not select the deployed design before measuring it.
