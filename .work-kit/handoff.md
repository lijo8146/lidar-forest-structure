# Local validation — 2026-10-14

- Real source SHA-256 matches the pinned upstream LFS object.
- 539,028 AOI returns processed after a buffered, chunked scan.
- 11 aligned GeoTIFF products plus LAZ, profile, figures and PDAL metadata; 18 product files hashed.
- 16 tests passed: units/CRS, grid edges, interpolation support, PDAL behavior, LAS/LAZ equivalence, filtering and output preservation.
- Actual final run validated, including counts, hashes, compound CRS and raster alignment.
- Walkthrough notebook executed successfully against final products; distributed source remains output-free.
- Four Quarto pages rendered and local links, images, current statistics and figure hashes passed checks.
- Headless Edge: four routes HTTP 200, no broken images, no JavaScript errors, no desktop/mobile overflow; mobile navigation opens.
- Desktop rendering visually inspected. Source code passes Ruff checks and was formatted.

Limitations: Windows local execution only; Linux GitHub CI is prepared but has not run. No independent scientific accuracy assessment. Example is mixed urban/woodland. Source reuse terms are not specified in its README, so point clouds are not redistributed. Environment inventory is a tested Windows inventory, not a portable lock. No remote or deployment configured.

Next: choose an empty GitHub repository, add its remote and push main. Review CI results, then enable manual Pages publishing if desired. Edit generated overview/quality prose in docs/report-templates. For scientific extension obtain licensed forest data and independent reference observations.
