# Write-up skeleton (MATS12_writeup_skeleton.docx)

Upload to Google Drive → open with Google Docs → set sharing to "anyone with the link".
Yellow boxes are where your own words go; grey italics are guide notes to delete.
Every table and number is copied from results_*.json, logbook.md and WRITEUP_KIT.md;
figures are embedded from figures/.

Rebuild after changing figures or logbook tables:
  python3 -c "..."  (the extraction that wrote writeup_content.json lives in the session log;
                     regenerate figures with 13_fig_anchoring_source.py and 14_fig_redraws.py)
  npm install docx@9 && node 15_build_writeup_skeleton.js
