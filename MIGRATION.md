# Migration from `flo-doo/cv`

Recommended target: `flo-doo/flo-doo.github.io`.

## Safe sequence

1. In the existing `cv` repository, create a preservation branch such as `archive/old-cv-site` from the current default branch.
2. Rename the repository from `cv` to `flo-doo.github.io`.
3. Replace the default-branch site files with this package.
4. In GitHub **Settings → Pages**, publish from the default branch/root if Pages is not already configured that way.
5. Run **Actions → Refresh publications → Run workflow** once to verify the publication updater.
6. Confirm `https://flo-doo.github.io/` and `https://flo-doo.github.io/publications.html` render correctly.

The archive branch keeps the previous site recoverable without maintaining it as the public homepage.
