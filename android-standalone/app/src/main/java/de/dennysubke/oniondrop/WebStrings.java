package de.dennysubke.oniondrop;

import android.content.Context;
import android.content.res.Configuration;
import de.dennysubke.oniondrop.core.WebText;
import java.util.EnumMap;

/** Load the same Android resources as the app, including the English fallback. */
final class WebStrings {
    static WebText snapshot(Context context) {
        context=context.createConfigurationContext(new Configuration(context.getResources().getConfiguration()));
        EnumMap<WebText.Key, String> strings = new EnumMap<>(WebText.Key.class);
        strings.put(WebText.Key.SEND_TITLE, context.getString(R.string.web_send_title));
        strings.put(WebText.Key.SEND_DESCRIPTION, context.getString(R.string.web_send_description));
        strings.put(WebText.Key.SAVE_FILE, context.getString(R.string.web_save_file));
        strings.put(WebText.Key.BYTES, context.getString(R.string.web_bytes));
        strings.put(WebText.Key.RECEIVE_TITLE, context.getString(R.string.web_receive_title));
        strings.put(WebText.Key.RECEIVE_DESCRIPTION, context.getString(R.string.web_receive_description));
        strings.put(WebText.Key.CHOOSE_FILES, context.getString(R.string.web_choose_files));
        strings.put(WebText.Key.SEND_FILES, context.getString(R.string.web_send_files));
        strings.put(WebText.Key.JAVASCRIPT_REQUIRED, context.getString(R.string.web_javascript_required));
        strings.put(WebText.Key.FOOTER, context.getString(R.string.web_footer));
        strings.put(WebText.Key.SELECT_FILES, context.getString(R.string.web_select_files));
        strings.put(WebText.Key.TOO_LARGE, context.getString(R.string.web_too_large));
        strings.put(WebText.Key.SENDING, context.getString(R.string.web_sending));
        strings.put(WebText.Key.TRANSFER_FAILED, context.getString(R.string.web_transfer_failed));
        strings.put(WebText.Key.FILES_SENT, context.getString(R.string.web_files_sent));
        strings.put(WebText.Key.NETWORK_FAILED, context.getString(R.string.web_network_failed));
        strings.put(WebText.Key.INVALID_HOST, context.getString(R.string.web_invalid_host));
        strings.put(WebText.Key.METHOD_NOT_ALLOWED, context.getString(R.string.web_method_not_allowed));
        strings.put(WebText.Key.NOT_FOUND, context.getString(R.string.web_not_found));
        strings.put(WebText.Key.REDIRECT, context.getString(R.string.web_redirect));
        strings.put(WebText.Key.FILE_NOT_FOUND, context.getString(R.string.web_file_not_found));
        strings.put(WebText.Key.ORIGIN_NOT_ALLOWED, context.getString(R.string.web_origin_not_allowed));
        strings.put(WebText.Key.UPLOAD_HEADER_REQUIRED, context.getString(R.string.web_upload_header_required));
        strings.put(WebText.Key.LENGTH_REQUIRED, context.getString(R.string.web_length_required));
        strings.put(WebText.Key.MAX_FILE_SIZE, context.getString(R.string.web_max_file_size));
        strings.put(WebText.Key.NAME_REQUIRED, context.getString(R.string.web_name_required));
        strings.put(WebText.Key.SAVE_FAILED, context.getString(R.string.web_save_failed));
        strings.put(WebText.Key.HEADERS_TOO_LARGE, context.getString(R.string.web_headers_too_large));
        strings.put(WebText.Key.INVALID_REQUEST, context.getString(R.string.web_invalid_request));
        strings.put(WebText.Key.INVALID_HEADER, context.getString(R.string.web_invalid_header));
        strings.put(WebText.Key.DUPLICATE_HEADER, context.getString(R.string.web_duplicate_header));
        strings.put(WebText.Key.CHUNKED_UNSUPPORTED, context.getString(R.string.web_chunked_unsupported));
        strings.put(WebText.Key.EXPECT_UNSUPPORTED, context.getString(R.string.web_expect_unsupported));
        strings.put(WebText.Key.INVALID_LENGTH, context.getString(R.string.web_invalid_length));
        strings.put(WebText.Key.INVALID_PATH, context.getString(R.string.web_invalid_path));
        strings.put(WebText.Key.CONNECTION_INTERRUPTED, context.getString(R.string.web_connection_interrupted));
        strings.put(WebText.Key.FILE_DOWNLOADED, context.getString(R.string.web_file_downloaded));
        strings.put(WebText.Key.FILE_RECEIVED, context.getString(R.string.web_file_received));
        return new WebText(context.getString(R.string.web_language), strings);
    }
    private WebStrings() {}
}
