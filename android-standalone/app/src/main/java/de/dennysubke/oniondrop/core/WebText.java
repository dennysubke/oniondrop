package de.dennysubke.oniondrop.core;

import java.util.EnumMap;
import java.util.Map;

/** One immutable language snapshot per HTTP request; the core has no Android dependency. */
public final class WebText {
    public enum Key {
        SEND_TITLE, SEND_DESCRIPTION, SAVE_FILE, BYTES,
        RECEIVE_TITLE, RECEIVE_DESCRIPTION, CHOOSE_FILES, SEND_FILES, JAVASCRIPT_REQUIRED,
        FOOTER, SELECT_FILES, TOO_LARGE, SENDING, TRANSFER_FAILED, FILES_SENT, NETWORK_FAILED,
        INVALID_HOST, METHOD_NOT_ALLOWED, NOT_FOUND, REDIRECT, FILE_NOT_FOUND,
        ORIGIN_NOT_ALLOWED, UPLOAD_HEADER_REQUIRED, LENGTH_REQUIRED, MAX_FILE_SIZE,
        NAME_REQUIRED, SAVE_FAILED, HEADERS_TOO_LARGE, INVALID_REQUEST, INVALID_HEADER,
        DUPLICATE_HEADER, CHUNKED_UNSUPPORTED, EXPECT_UNSUPPORTED, INVALID_LENGTH, INVALID_PATH,
        CONNECTION_INTERRUPTED, FILE_DOWNLOADED, FILE_RECEIVED
    }

    public final String language;
    private final EnumMap<Key, String> strings = new EnumMap<>(Key.class);

    public WebText(String language, Map<Key, String> strings) {
        if (!language.matches("en|de|es|fr|it|ru|zh|ja")) throw new IllegalArgumentException("Unsupported web language");
        this.language = language;
        this.strings.putAll(strings);
        for (Key key : Key.values()) {
            if (get(key) == null || get(key).isEmpty()) throw new IllegalArgumentException("Missing web translation: " + key);
        }
    }

    public String get(Key key) { return strings.get(key); }
    public String html(Key key) { return DropSecurity.html(get(key)); }
}
