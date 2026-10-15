# Processing decisions

1. Use a real-data example. Synthetic fixtures are only used for known numerical test behavior.
2. Use supplied Autzen labels for an available comparison; this is mixed urban/woodland, not a representative forest benchmark.
3. Separate horizontal/vertical units, retain NAVD88, reject unreviewed datum transformations.
4. Preserve source labels. Ground disagreement is not accuracy.
5. Limit IDW support and publish missing support; do not fill all holes for aesthetics.
6. Preserve negative heights and expose artifacts.
7. Separate all-class surface height from vegetation p95. Neither is fuel load or fire risk.
8. Keep point data out of Git; retain attribution and unknown upstream reuse terms.
9. Use run-specific hashes, not cross-platform binary identity.
10. Stage outputs and refuse overwrite.

## Next scientific steps

Obtain an explicitly licensed forest-only dataset with acquisition metadata and independent checkpoints or plots. Test parameters across slope and canopy strata. Review ground labels manually; validate terrain against independent checkpoints. Establish sampling uncertainty before ecological inference.
