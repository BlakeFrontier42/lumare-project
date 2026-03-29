# LUMARE — UI Artifacts & Existing Mockups

---

## Existing React Mockup Artifacts

The following Claude artifact links contain the existing React JSX mockups. These are the current UI implementations that need to be converted to Next.js and elevated for desktop.

### Artifact Links
1. **Version A**: https://claude.ai/public/artifacts/8230fedf-390c-44ef-b4b1-2445d1c54695
2. **Version B**: https://claude.ai/public/artifacts/eebc5e0d-2c12-4e3d-85d8-5f232aa24c2b
3. **Version C**: https://claude.ai/public/artifacts/62af8dcb-ad56-421a-8c8e-f967ab35a047

### Important Notes
- **These links require authentication** — you must be logged into Claude to view them
- **Some versions differ**: One has a macro aspect that allows portfolio building, which disappeared in the most recent version. This feature needs to be restored.
- **The Plan tab** existed in an earlier version but was dropped. Needs to be re-added.
- All versions are single-file React JSX (lumare_v3.jsx style)

### How to Extract
1. Open each link in a browser while logged into Claude
2. Copy the JSX code from each artifact
3. Save as:
   - `ui/lumare_artifact_v1.jsx`
   - `ui/lumare_artifact_v2.jsx`
   - `ui/lumare_artifact_v3.jsx`
4. Compare versions to identify the macro/portfolio builder feature that was lost

---

## What to Blend from Each Version

| Feature | Status | Which Version | Action |
|---------|--------|---------------|--------|
| 5-tab nav (Home/Markets/Intel/Macro/Profile) | ✅ In current | Latest | Keep |
| Strategy Marketplace | ✅ In current | Latest | Keep |
| Risk War Room | ✅ In current | Latest | Keep |
| Portfolio Builder (6-step) | ✅ In current | Latest | Keep |
| Macro Portfolio Building aspect | ❌ Missing | Earlier version | Restore from earlier, blend in |
| Plan tab (Financial Planning) | ❌ Missing | Earlier version | Restore from earlier, add to nav |
| Mobile layout | ✅ Strong | Latest | Keep as-is for mobile breakpoint |
| Desktop layout | ⚠️ Weak | All versions | Rebuild per UI_DESIGN.md specs |

---

## File Naming Convention (for saved artifacts)

```
ui/
├── lumare_artifact_v1.jsx    # First artifact (copy from link 1)
├── lumare_artifact_v2.jsx    # Second artifact (copy from link 2)
├── lumare_artifact_v3.jsx    # Third artifact (copy from link 3)
└── ARTIFACTS_README.md       # This file
```

**ACTION REQUIRED**: The user needs to manually open the artifact links, copy the JSX code, and paste it into these files. The links are not accessible programmatically.
