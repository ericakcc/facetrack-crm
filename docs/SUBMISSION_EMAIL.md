# Submission Email Draft — to Mike Rubino

**Send to**: mike@aifund.ai
**Subject**: FaceTrack CRM — Build Challenge submission

**Fill in the bracketed placeholders before sending.** Everything else is ready.

---

> Hi Mike,
>
> Submitting the Build Challenge for the Beauty Clinic OS venture.
>
> - **Working prototype**: [STREAMLIT_CLOUD_URL] (auto-seeds 3 demo patients on first load; try the 📸 新增就診 flow with the photos under `data/test_images/` — the consistency gate will reject the under- and over-exposed faces and accept the third)
> - **Demo video (3–4 min)**: [LOOM_URL]
> - **Source**: https://github.com/ericakcc/facetrack-crm
> - **PRD / TDD / authorship note**: `docs/PRD.md`, `docs/TDD.md`, `docs/BUILD_NOTES.md` in the repo
>
> A few things worth flagging before you watch:
>
> 1. The scoring engine is deterministic CV (`scripts/reproducibility_evidence.py` plus the embedded chart in TDD §3 makes this concrete) — the LLM only translates scores into 繁中 prose and an editable treatment-plan draft.
> 2. The Photo-Consistency Gate is the depth area, and it's demonstrated on camera rejecting two real photos and accepting one — per the panel-visibility rule.
> 3. End-to-end pipeline is 17 ms p50 on Apple Silicon (`scripts/benchmark.py`); Claude inference is ~$0.005 per visit at current Sonnet 4.6 pricing.
>
> Happy to walk through anything you'd like to dig into.
>
> Thanks for the opportunity,
> Eric Tsou
> erictsou@softstargames.com.tw

---

## Before sending checklist

- [ ] Replace `[STREAMLIT_CLOUD_URL]` with the live deploy URL
- [ ] Replace `[LOOM_URL]` with the public Loom share link
- [ ] Verify both URLs open in an incognito window
- [ ] Verify `data/test_images/` is browseable on GitHub (i.e., not gitignored)
- [ ] Optional: add CC to anyone Mike has been looping in
- [ ] If submitting later than 2026-05-19, prepend one sentence: "Sending slightly past the default 48hr — wanted to ship the reproducibility evidence chart properly."
