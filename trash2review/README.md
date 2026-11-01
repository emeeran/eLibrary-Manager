# trash2review — holding pen, NOT a deletion

Files here were moved by the cleanup pipeline because they looked redundant,
dead, or superseded. **Nothing is deleted.** A human reviews this folder and
empties it deliberately.

To restore a file to its original location:

```bash
git mv trash2review/<original-relative-path> <original-relative-path>
git commit -m "restore <path>"
```

The mirrored directory structure matches where each file used to live.
