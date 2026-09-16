package de.dennysubke.oniondrop.core;

import java.io.File;

public final class DropFile {
    public final String id, name, mime;
    public final File file;
    public final long size, createdAt;
    public DropFile(String id, String name, String mime, File file, long size, long createdAt) {
        this.id=id;this.name=name;this.mime=mime;this.file=file;this.size=size;this.createdAt=createdAt;
    }
}
