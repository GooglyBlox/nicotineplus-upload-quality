# Upload Quality

This plugin adds a `Quality` column to Nicotine+'s uploads tab so you can see things like `44.1 kHz / 16 bit`, `96 kHz / 24 bit`, or `320 kbps` next to the files you're sending.

<img width="2555" height="1220" alt="image" src="https://github.com/user-attachments/assets/5de5f398-b467-40d1-9808-090f197016f5" />

It does work, but it does not work in a clean or officially supported way.

Nicotine+ does not expose a real plugin API for adding columns to that view, so this plugin monkey-patches the live uploads table at runtime. In other words: this is a gimmicky hack. A fun one, and apparently a useful one, but still a hack.

## What To Expect

When it behaves, it feels pretty natural. The plugin adds a `Quality` column to the uploads list and fills it from local file metadata. Lossless files should usually show sample rate and bit depth. Lossy files should usually show bitrate.

Behind the scenes it tries a few metadata sources in order:

Nicotine+'s existing `transfer.file_attributes`, then Nicotine+'s bundled `TinyTag`, then `mutagen` if you happen to have it available in the plugin environment, then a couple of built-in parsers for formats like FLAC, WAV, and AIFF. If all of that fails for a lossy file and there is enough information available, it can fall back to estimating bitrate from file size and duration.

## Caveats

This has only been tested on Nicotine+ `3.3.10`, GTK `4.16.12`, and Python `3.12.9`.

If you are on a different Nicotine+, GTK, or Python version, this may still work, but it may also break partially, break completely, or do something weird enough that the correct move is just to disable it and restart Nicotine+.

This should be treated as experimental and version-fragile. It relies on Nicotine+ internals that can change at any time. A Nicotine+ update, a GTK update, or a Python update could be enough to break it.

If the uploads UI starts acting strange after enabling the plugin, disable it and restart the app before assuming anything worse is going on.

If you have a very large uploads list, the plugin may take a long time to fill in the `Quality` column for all the old rows. It may need to walk a lot of upload history and inspect a lot of local files to backfill metadata.

That means Nicotine+ may freeze for minutes or longer while it catches up. That is not abnormal for this plugin.

## Installing

The intended install method is the zip from [GitHub Releases](https://github.com/GooglyBlox/nicotineplus-upload-quality/releases). Then, extract it into your plugins folder.

Once it's installed, enable `Upload Quality`, open the uploads tab, and give it a moment. The plugin waits for the window to exist, patches the uploads view, and then starts filling in the new column.
