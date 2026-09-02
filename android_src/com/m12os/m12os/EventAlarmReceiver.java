package com.m12os.m12os;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

public class EventAlarmReceiver extends BroadcastReceiver {

    private static final String TAG = "M12EventReceiver";

    private static final String ACTION_EVENT_REMINDER =
            "com.m12os.EVENT_REMINDER";

    private static final String ACTION_EVENT_TIME =
            "com.m12os.EVENT_TIME";

    private static final String ACTION_EVENT_STOP =
            "com.m12os.EVENT_STOP";

    private static final String CHANNEL_ID =
            "m12_event_notifications_v2";

    // Event notification ID settings.
    // Calendar uses multiple notification IDs so different events
    // do not overwrite each other.
    private static final int NOTIFICATION_ID_BASE = 22000;
    private static final int NOTIFICATION_ID_RANGE = 10000;

    // How long the event sound plays before stopping automatically.
    private static final int AUTO_STOP_MS = 14000;

    private static Ringtone activeRingtone = null;


    @Override
    public void onReceive(Context context, Intent intent) {

        String action =
                intent != null ? intent.getAction() : null;

        Log.i(TAG, "RECEIVED action=" + action);

        if (ACTION_EVENT_STOP.equals(action)) {
            stopEventSound();
            return;
        }

        if (!ACTION_EVENT_REMINDER.equals(action)
                && !ACTION_EVENT_TIME.equals(action)) {

            Log.w(
                    TAG,
                    "Ignoring unknown action: " + action
            );
            return;
        }

        PowerManager.WakeLock wakeLock = null;

        try {

            PowerManager pm =
                    (PowerManager) context.getSystemService(
                            Context.POWER_SERVICE
                    );

            if (pm != null) {

                wakeLock = pm.newWakeLock(
                        PowerManager.PARTIAL_WAKE_LOCK,
                        "M12OS:EventNotification"
                );

                wakeLock.acquire(10000);

                Log.i(
                        TAG,
                        "WAKELOCK ACQUIRED"
                );
            }

            createNotificationChannel(context);

            postNotification(
                    context,
                    intent,
                    action
            );

            playEventSound(context);

            /*
             * EVENT_REMINDER is only the pre-event warning.
             * EVENT_TIME owns recurrence so the next occurrence
             * is scheduled exactly once.
             */
            if (ACTION_EVENT_TIME.equals(action)) {
                scheduleNextRepeat(
                        context,
                        intent
                );
            }

        } catch (Exception error) {

            Log.e(
                    TAG,
                    "Event notification failed",
                    error
            );

        } finally {

            try {

                if (
                        wakeLock != null
                                && wakeLock.isHeld()
                ) {

                    wakeLock.release();

                    Log.i(
                            TAG,
                            "WAKELOCK RELEASED"
                    );
                }

            } catch (Exception error) {

                Log.e(
                        TAG,
                        "WakeLock release failed",
                        error
                );
            }
        }
    }


    private void scheduleNextRepeat(
            Context context,
            Intent sourceIntent
    ) {

        if (sourceIntent == null) {
            return;
        }


        String repeatMode =
                sourceIntent.getStringExtra(
                        "repeat_mode"
                );

        if (repeatMode == null) {
            repeatMode = "once";
        }

        repeatMode = repeatMode.trim();

        if (
                repeatMode.isEmpty()
                        || "once".equals(repeatMode)
        ) {
            Log.i(
                    TAG,
                    "NO NEXT EVENT repeat=once"
            );
            return;
        }

        String eventDate =
                safeExtra(
                        sourceIntent,
                        "event_date"
                );

        String eventTime =
                safeExtra(
                        sourceIntent,
                        "event_time"
                );

        String days =
                safeExtra(
                        sourceIntent,
                        "days"
                );

        String untilDate =
                safeExtra(
                        sourceIntent,
                        "until_date"
                );

        int reminderMinutes =
                sourceIntent.getIntExtra(
                        "event_reminder_minutes",
                        -1
                );

        int reminderRequestCode =
                sourceIntent.getIntExtra(
                        "reminder_request_code",
                        -1
                );

        int timeRequestCode =
                sourceIntent.getIntExtra(
                        "time_request_code",
                        -1
                );

        if (
                reminderRequestCode < 0
                        || timeRequestCode < 0
        ) {
            Log.w(
                    TAG,
                    "Missing event request codes"
            );
            return;
        }

        Calendar base =
                parseEventDateTime(
                        eventDate,
                        eventTime
                );

        if (base == null) {
            Log.w(
                    TAG,
                    "Invalid event date/time"
            );
            return;
        }

        Calendar now =
                Calendar.getInstance();

        Calendar candidate = null;

        if ("yearly".equals(repeatMode)) {

            int month =
                    base.get(
                            Calendar.MONTH
                    );

            int day =
                    base.get(
                            Calendar.DAY_OF_MONTH
                    );

            int hour =
                    base.get(
                            Calendar.HOUR_OF_DAY
                    );

            int minute =
                    base.get(
                            Calendar.MINUTE
                    );

            for (
                    int yearOffset = 0;
                    yearOffset <= 8;
                    yearOffset++
            ) {

                Calendar test =
                        Calendar.getInstance();

                test.setLenient(false);

                try {

                    test.set(
                            now.get(Calendar.YEAR)
                                    + yearOffset,
                            month,
                            day,
                            hour,
                            minute,
                            0
                    );

                    test.set(
                            Calendar.MILLISECOND,
                            0
                    );

                    /*
                     * Force Calendar validation so February 29
                     * correctly skips non-leap years.
                     */
                    test.getTime();

                } catch (Exception error) {
                    continue;
                }

                if (
                        test.getTimeInMillis()
                                <= now.getTimeInMillis()
                ) {
                    continue;
                }

                if (
                        isAfterUntil(
                                test,
                                untilDate
                        )
                ) {
                    return;
                }

                candidate = test;
                break;
            }

        } else if (
                "every_day".equals(repeatMode)
                        || "days".equals(repeatMode)
        ) {

            int hour =
                    base.get(
                            Calendar.HOUR_OF_DAY
                    );

            int minute =
                    base.get(
                            Calendar.MINUTE
                    );

            for (
                    int offset = 1;
                    offset <= 370;
                    offset++
            ) {

                Calendar test =
                        (Calendar) now.clone();

                test.add(
                        Calendar.DAY_OF_YEAR,
                        offset
                );

                test.set(
                        Calendar.HOUR_OF_DAY,
                        hour
                );

                test.set(
                        Calendar.MINUTE,
                        minute
                );

                test.set(
                        Calendar.SECOND,
                        0
                );

                test.set(
                        Calendar.MILLISECOND,
                        0
                );

                if (
                        isAfterUntil(
                                test,
                                untilDate
                        )
                ) {
                    return;
                }

                if (
                        "days".equals(repeatMode)
                                && !dayIsAllowed(
                                        test,
                                        days
                                )
                ) {
                    continue;
                }

                candidate = test;
                break;
            }

        } else {

            Log.w(
                    TAG,
                    "Unknown repeat mode="
                            + repeatMode
            );
            return;
        }

        if (candidate == null) {

            Log.i(
                    TAG,
                    "NO NEXT EVENT"
            );
            return;
        }

        scheduleOccurrence(
                context,
                sourceIntent,
                candidate,
                reminderMinutes,
                reminderRequestCode,
                timeRequestCode
        );
    }


    private void scheduleOccurrence(
            Context context,
            Intent sourceIntent,
            Calendar occurrence,
            int reminderMinutes,
            int reminderRequestCode,
            int timeRequestCode
    ) {

        String eventTitle =
                safeExtra(
                        sourceIntent,
                        "event_title"
                );

        AlarmManager manager =
                (AlarmManager)
                        context.getSystemService(
                                Context.ALARM_SERVICE
                        );

        if (manager == null) {

            Log.w(
                    TAG,
                    "AlarmManager unavailable"
            );
            return;
        }

        if (
                Build.VERSION.SDK_INT >= 31
                        && !manager.canScheduleExactAlarms()
        ) {

            Log.w(
                    TAG,
                    "Exact event alarms are not permitted"
            );
            return;
        }

        PendingIntent timeIntent =
                createEventPendingIntent(
                        context,
                        sourceIntent,
                        ACTION_EVENT_TIME,
                        timeRequestCode,
                        occurrence
                );

        scheduleExact(
                manager,
                occurrence.getTimeInMillis(),
                timeIntent
        );

        Log.i(
                TAG,
                "NEXT EVENT_TIME SCHEDULED "
                        + "title="
                        + eventTitle
                        + " "
                        + formatCalendar(
                                occurrence
                        )
        );

        if (reminderMinutes > 0) {

            Calendar reminder =
                    (Calendar)
                            occurrence.clone();

            reminder.add(
                    Calendar.MINUTE,
                    -reminderMinutes
            );

            if (
                    reminder.getTimeInMillis()
                            > System.currentTimeMillis()
            ) {

                PendingIntent reminderIntent =
                        createEventPendingIntent(
                                context,
                                sourceIntent,
                                ACTION_EVENT_REMINDER,
                                reminderRequestCode,
                                occurrence
                        );

                scheduleExact(
                        manager,
                        reminder.getTimeInMillis(),
                        reminderIntent
                );

                Log.i(
                        TAG,
                        "NEXT EVENT_REMINDER SCHEDULED "
                                + "title="
                                + eventTitle
                                + " "
                                + formatCalendar(
                                        reminder
                                )
                );
            }
        }
    }


    private PendingIntent createEventPendingIntent(
            Context context,
            Intent sourceIntent,
            String action,
            int requestCode,
            Calendar occurrence
    ) {

        Intent nextIntent =
                new Intent(
                        context,
                        EventAlarmReceiver.class
                );

        nextIntent.setAction(
                action
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "event_title"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "event_notes"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "event_reminder"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "event_date"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "event_time"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "repeat_mode"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "days"
        );

        copyStringExtra(
                sourceIntent,
                nextIntent,
                "until_date"
        );

        nextIntent.putExtra(
                "event_reminder_minutes",
                sourceIntent.getIntExtra(
                        "event_reminder_minutes",
                        -1
                )
        );

        nextIntent.putExtra(
                "reminder_request_code",
                sourceIntent.getIntExtra(
                        "reminder_request_code",
                        -1
                )
        );

        nextIntent.putExtra(
                "time_request_code",
                sourceIntent.getIntExtra(
                        "time_request_code",
                        -1
                )
        );

        nextIntent.putExtra(
                "event_datetime",
                formatCalendar(
                        occurrence
                )
        );

        int flags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            flags |=
                    PendingIntent.FLAG_IMMUTABLE;
        }

        return PendingIntent.getBroadcast(
                context,
                requestCode,
                nextIntent,
                flags
        );
    }


    private void scheduleExact(
            AlarmManager manager,
            long triggerMillis,
            PendingIntent pendingIntent
    ) {

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {

            manager.setExactAndAllowWhileIdle(
                    AlarmManager.RTC_WAKEUP,
                    triggerMillis,
                    pendingIntent
            );

        } else {

            manager.setExact(
                    AlarmManager.RTC_WAKEUP,
                    triggerMillis,
                    pendingIntent
            );
        }
    }


    private Calendar parseEventDateTime(
            String dateText,
            String timeText
    ) {

        try {

            String normalizedTime =
                    timeText == null
                            || timeText.trim().isEmpty()
                            ? "00:00"
                            : timeText.trim();

            SimpleDateFormat format =
                    new SimpleDateFormat(
                            "yyyy-MM-dd HH:mm",
                            Locale.US
                    );

            format.setLenient(false);

            Calendar result =
                    Calendar.getInstance();

            result.setTime(
                    format.parse(
                            dateText.trim()
                                    + " "
                                    + normalizedTime
                    )
            );

            return result;

        } catch (Exception error) {

            Log.e(
                    TAG,
                    "Event date parse failed",
                    error
            );

            return null;
        }
    }


    private boolean dayIsAllowed(
            Calendar candidate,
            String days
    ) {

        if (
                days == null
                        || days.trim().isEmpty()
        ) {
            return false;
        }

        String wanted;

        switch (
                candidate.get(
                        Calendar.DAY_OF_WEEK
                )
        ) {

            case Calendar.MONDAY:
                wanted = "Mon";
                break;

            case Calendar.TUESDAY:
                wanted = "Tue";
                break;

            case Calendar.WEDNESDAY:
                wanted = "Wed";
                break;

            case Calendar.THURSDAY:
                wanted = "Thu";
                break;

            case Calendar.FRIDAY:
                wanted = "Fri";
                break;

            case Calendar.SATURDAY:
                wanted = "Sat";
                break;

            case Calendar.SUNDAY:
                wanted = "Sun";
                break;

            default:
                return false;
        }

        String[] values =
                days.split(",");

        for (String value : values) {

            if (
                    wanted.equals(
                            value.trim()
                    )
            ) {
                return true;
            }
        }

        return false;
    }


    private boolean isAfterUntil(
            Calendar candidate,
            String untilDate
    ) {

        if (
                untilDate == null
                        || untilDate.trim().isEmpty()
        ) {
            return false;
        }

        String candidateDate =
                new SimpleDateFormat(
                        "yyyy-MM-dd",
                        Locale.US
                ).format(
                        candidate.getTime()
                );

        return candidateDate.compareTo(
                untilDate.trim()
        ) > 0;
    }


    private String safeExtra(
            Intent intent,
            String key
    ) {

        String value =
                intent.getStringExtra(
                        key
                );

        return value == null
                ? ""
                : value.trim();
    }


    private void copyStringExtra(
            Intent source,
            Intent destination,
            String key
    ) {

        String value =
                source.getStringExtra(
                        key
                );

        if (value != null) {

            destination.putExtra(
                    key,
                    value
            );
        }
    }


    private String formatCalendar(
            Calendar calendar
    ) {

        return new SimpleDateFormat(
                "yyyy-MM-dd HH:mm",
                Locale.US
        ).format(
                calendar.getTime()
        );
    }


    private void createNotificationChannel(
            Context context
    ) {

        if (
                Build.VERSION.SDK_INT
                        < Build.VERSION_CODES.O
        ) {
            return;
        }

        NotificationManager manager =
                (NotificationManager)
                        context.getSystemService(
                                Context.NOTIFICATION_SERVICE
                        );

        if (manager == null) {
            return;
        }

        if (
                manager.getNotificationChannel(
                        CHANNEL_ID
                ) != null
        ) {
            return;
        }

        NotificationChannel channel =
                new NotificationChannel(
                        CHANNEL_ID,
                        "M12 Calendar Events",
                        NotificationManager.IMPORTANCE_HIGH
                );

        channel.setDescription(
                "M12 OS calendar event reminders"
        );

        channel.enableVibration(true);

        /*
         * Sound is played manually by playEventSound().
         * The notification channel itself stays silent
         * to prevent double playback.
         */
        channel.setSound(null, null);

        manager.createNotificationChannel(
                channel
        );

        Log.i(
                TAG,
                "NOTIFICATION CHANNEL CREATED"
        );
    }


    private void postNotification(
            Context context,
            Intent sourceIntent,
            String action
    ) {

        NotificationManager manager =
                (NotificationManager)
                        context.getSystemService(
                                Context.NOTIFICATION_SERVICE
                        );

        if (manager == null) {
            return;
        }

        String title = "M12 Event";
        String notes = "";
        String eventDateTime = "";

        if (sourceIntent != null) {

            String value =
                    sourceIntent.getStringExtra(
                            "event_title"
                    );

            if (
                    value != null
                            && !value.trim().isEmpty()
            ) {

                title = value.trim();
            }

            value =
                    sourceIntent.getStringExtra(
                            "event_notes"
                    );

            if (value != null) {
                notes = value.trim();
            }

            value =
                    sourceIntent.getStringExtra(
                            "event_datetime"
                    );

            if (value != null) {
                eventDateTime = value.trim();
            }
        }

        Intent openIntent =
                context.getPackageManager()
                        .getLaunchIntentForPackage(
                                context.getPackageName()
                        );

        PendingIntent contentIntent = null;

        if (openIntent != null) {

            openIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_CLEAR_TOP
            );

            int flags =
                    PendingIntent.FLAG_UPDATE_CURRENT;

            if (
                    Build.VERSION.SDK_INT
                            >= Build.VERSION_CODES.M
            ) {

                flags |=
                        PendingIntent.FLAG_IMMUTABLE;
            }

            contentIntent =
                    PendingIntent.getActivity(
                            context,
                            22051,
                            openIntent,
                            flags
                    );
        }

        String body;

        if (
                ACTION_EVENT_REMINDER.equals(
                        action
                )
        ) {

            body =
                    "Event in 5 minutes";

            if (!eventDateTime.isEmpty()) {
                body += "\n" + eventDateTime;
            }

        } else {

            body =
                    notes.isEmpty()
                            ? "Event time"
                            : notes;

            if (
                    body.isEmpty()
                            && !eventDateTime.isEmpty()
            ) {
                body = eventDateTime;
            }
        }

        Notification.Builder builder;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.O
        ) {

            builder =
                    new Notification.Builder(
                            context,
                            CHANNEL_ID
                    );

        } else {

            builder =
                    new Notification.Builder(
                            context
                    );

            builder.setDefaults(
                    Notification.DEFAULT_VIBRATE
            );
        }

        builder.setSmallIcon(
                context.getApplicationInfo().icon
        );

        builder.setContentTitle(
                title
        );

        builder.setContentText(
                body
        );

        builder.setStyle(
                new Notification.BigTextStyle()
                        .bigText(body)
        );

        builder.setAutoCancel(true);

        builder.setPriority(
                Notification.PRIORITY_HIGH
        );

        builder.setCategory(
                Notification.CATEGORY_EVENT
        );

        builder.setVisibility(
                Notification.VISIBILITY_PUBLIC
        );

        if (contentIntent != null) {

            builder.setContentIntent(
                    contentIntent
            );
        }

        int notificationId =
                NOTIFICATION_ID_BASE
                        + Math.abs(
                        (
                                title
                                        + eventDateTime
                                        + action
                        ).hashCode()
                ) % NOTIFICATION_ID_RANGE;

        manager.notify(
                notificationId,
                builder.build()
        );

        Log.i(
                TAG,
                "EVENT NOTIFICATION POSTED action="
                        + action
                        + " title="
                        + title
        );
    }


    private void playEventSound(
            Context context
    ) {

        try {

            stopEventSound();

            Uri soundUri =
                    RingtoneManager.getDefaultUri(
                            RingtoneManager.TYPE_ALARM
                    );

            if (soundUri == null) {

                soundUri =
                        RingtoneManager.getDefaultUri(
                                RingtoneManager.TYPE_NOTIFICATION
                        );
            }

            if (soundUri == null) {

                Log.w(
                        TAG,
                        "No event sound URI available"
                );

                return;
            }

            activeRingtone =
                    RingtoneManager.getRingtone(
                            context,
                            soundUri
                    );

            if (activeRingtone == null) {
                return;
            }

            if (
                    Build.VERSION.SDK_INT
                            >= Build.VERSION_CODES.P
            ) {

                activeRingtone.setLooping(true);
            }

            activeRingtone.play();

            Log.i(
                    TAG,
                    "EVENT SOUND PLAYING"
            );

            /*
             * Automatically stop after 7 seconds.
             */
            new Handler(
                    Looper.getMainLooper()
            ).postDelayed(
                    EventAlarmReceiver::stopEventSound,
                    AUTO_STOP_MS
            );

        } catch (Exception error) {

            Log.e(
                    TAG,
                    "Event sound failed",
                    error
            );
        }
    }


    private static synchronized void stopEventSound() {

        try {

            if (
                    activeRingtone != null
                            && activeRingtone.isPlaying()
            ) {

                activeRingtone.stop();
            }

        } catch (Exception error) {

            Log.e(
                    TAG,
                    "Stop event sound failed",
                    error
            );

        } finally {

            activeRingtone = null;
        }

        Log.i(
                TAG,
                "EVENT SOUND STOPPED"
        );
    }
}