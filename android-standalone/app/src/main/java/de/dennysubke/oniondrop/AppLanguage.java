package de.dennysubke.oniondrop;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.LocaleManager;
import android.content.Context;
import android.content.res.Configuration;
import android.os.Build;
import android.os.LocaleList;
import java.util.Locale;

/** Uses Android's app language setting, with a local fallback for Android 8–12. */
final class AppLanguage {
    private static final String[] TAGS = {"", "de", "en", "es", "fr", "it", "ru", "zh", "ja"};
    static Context wrap(Context context) {
        if (Build.VERSION.SDK_INT >= 33) return context;
        String tag = context.getSharedPreferences("preferences", Context.MODE_PRIVATE).getString("language", "");
        if (tag.isEmpty()) return context;
        Configuration configuration = new Configuration(context.getResources().getConfiguration());
        configuration.setLocale(Locale.forLanguageTag(tag));
        return context.createConfigurationContext(configuration);
    }
    static void choose(Activity activity) {
        String current;
        if (Build.VERSION.SDK_INT >= 33) current = activity.getSystemService(LocaleManager.class).getApplicationLocales().toLanguageTags();
        else current = activity.getSharedPreferences("preferences", Context.MODE_PRIVATE).getString("language", "");
        int selected = 0;
        for (int i=1; i<TAGS.length; i++) if (current.equals(TAGS[i])) selected=i;
        String[] labels = {activity.getString(R.string.system_language), "Deutsch", "English", "Español", "Français", "Italiano", "Русский", "中文", "日本語"};
        new AlertDialog.Builder(activity).setTitle(R.string.language)
            .setSingleChoiceItems(labels, selected, (dialog, index) -> {
                dialog.dismiss();
                if (Build.VERSION.SDK_INT >= 33) activity.getSystemService(LocaleManager.class).setApplicationLocales(LocaleList.forLanguageTags(TAGS[index]));
                else {
                    activity.getSharedPreferences("preferences", Context.MODE_PRIVATE).edit().putString("language", TAGS[index]).apply();
                    activity.recreate();
                }
            }).setNegativeButton(R.string.cancel, null).show();
    }
}
