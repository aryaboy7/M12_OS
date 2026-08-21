package com.m12os.m12os;

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
import android.os.PowerManager;
import android.util.Log;

public class EventAlarmReceiver extends BroadcastReceiver {

    private static final String TAG =
            "M12EventReceiver";

    private static final String ACTION_EVENT_REMINDER =
            "com.m12os.EVENT_REMINDER";

    private static final String ACTION_EVENT_TIME =
            "com.m12os.EVENT_TIME";

    private static final String ACTION_EVENT_STOP =
            "com.m12os.EVENT_STOP";

    private static final String CHANNEL_ID =
            "m12_event_notifications_v3";

    private static final int REMINDER_STOP_MS =
            7000;

    private static final int EVENT_TIME_STOP_MS =
            14000;

    private static Ringtone activeRingtone;
    private static PowerManager.WakeLock wakeLock;

    @Override
    public void onReceive(
            Context context,
            Intent intent
    ) {
        String action =
                intent != null
                        ? intent.getAction()
                        : null;

        Log.i(
                TAG,
                "RECEIVED action=" + action
        );

        if (ACTION_EVENT_STOP.equals(action)) {
            stopEventSound();
            return;
        }

        if (
                !ACTION_EVENT_REMINDER.equals(action)
                && !ACTION_EVENT_TIME.equals(action)
        ) {
            Log.w(
                    TAG,
                    "Ignoring unknown action: " + action
            );
            return;
        }

        acquireWakeLock(context);

        try {
            createNotificationChannel(context);
            postNotification(
                    context,
                    intent,
                    action
            );
            playEventSound(context, action);

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Event notification failed",
                    error
            );
            stopEventSound();
        }
    }

    private void acquireWakeLock(
            Context context
    ) {
        try {
            if (
                    wakeLock != null
                    && wakeLock.isHeld()
            ) {
                wakeLock.release();
            }

            PowerManager pm =
                    (PowerManager)
                            context.getSystemService(
                                    Context.POWER_SERVICE
                            );

            if (pm == null) {
                return;
            }

            wakeLock = pm.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "M12OS:EventNotification"
            );

            wakeLock.acquire(15000);

            Log.i(
                    TAG,
                    "WAKELOCK ACQUIRED"
            );

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "WakeLock failed",
                    error
            );
        }
    }

    private void releaseWakeLock() {
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

        wakeLock = null;
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
         * Keep notification channel silent.
         * The ringtone below is controlled explicitly so M12 can
         * stop it after 7 seconds or when Calendar is opened.
         */
        channel.setSound(
                null,
                null
        );

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

        String title = getStringExtra(
                sourceIntent,
                "event_title",
                "M12 Event"
        );

        String notes = getStringExtra(
                sourceIntent,
                "event_notes",
                ""
        );

        String eventDateTime = getStringExtra(
                sourceIntent,
                "event_datetime",
                ""
        );

        int reminderMinutes = 0;

        if (sourceIntent != null) {
            reminderMinutes =
                    sourceIntent.getIntExtra(
                            "event_reminder_minutes",
                            0
                    );
        }

        String body;

        if (
                ACTION_EVENT_REMINDER.equals(
                        action
                )
        ) {
            body = reminderText(
                    reminderMinutes
            );
        } else {
            body = "Event time";
        }

        if (!notes.isEmpty()) {
            body += "\n" + notes;
        } else if (!eventDateTime.isEmpty()) {
            body += "\n" + eventDateTime;
        }

        Intent stopIntent =
                new Intent(
                        context,
                        EventAlarmReceiver.class
                );

        stopIntent.setAction(
                ACTION_EVENT_STOP
        );

        int stopFlags =
                PendingIntent.FLAG_UPDATE_CURRENT;

        if (
                Build.VERSION.SDK_INT
                        >= Build.VERSION_CODES.M
        ) {
            stopFlags |=
                    PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent stopPendingIntent =
                PendingIntent.getBroadcast(
                        context,
                        22999,
                        stopIntent,
                        stopFlags
                );

        Intent openIntent =
                context.getPackageManager()
                        .getLaunchIntentForPackage(
                                context.getPackageName()
                        );

        PendingIntent contentIntent =
                null;

        if (openIntent != null) {
            openIntent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_CLEAR_TOP
            );

            int openFlags =
                    PendingIntent.FLAG_UPDATE_CURRENT;

            if (
                    Build.VERSION.SDK_INT
                            >= Build.VERSION_CODES.M
            ) {
                openFlags |=
                        PendingIntent.FLAG_IMMUTABLE;
            }

            contentIntent =
                    PendingIntent.getActivity(
                            context,
                            22998,
                            openIntent,
                            openFlags
                    );
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
                Notification.PRIORITY_MAX
        );

        builder.setCategory(
                Notification.CATEGORY_EVENT
        );

        builder.setVisibility(
                Notification.VISIBILITY_PUBLIC
        );

        builder.addAction(
                new Notification.Action.Builder(
                        0,
                        "STOP",
                        stopPendingIntent
                ).build()
        );

        if (contentIntent != null) {
            builder.setContentIntent(
                    contentIntent
            );
        }

        int actionOffset =
                ACTION_EVENT_REMINDER.equals(
                        action
                )
                        ? 0
                        : 10000;

        int notificationId =
                22000
                        + actionOffset
                        + Math.abs(
                                (
                                        title
                                                + eventDateTime
                                ).hashCode()
                        ) % 9000;

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

    private String reminderText(
            int minutes
    ) {
        if (minutes <= 0) {
            return "Upcoming event";
        }

        if (minutes == 60) {
            return "1 hour before event";
        }

        if (minutes == 1440) {
            return "1 day before event";
        }

        if (minutes % 60 == 0) {
            return (minutes / 60)
                    + " hours before event";
        }

        return minutes
                + " minutes before event";
    }

    private void playEventSound(
            Context context,
            String action
    ) {
        stopRingtoneOnly();

        try {
            /*
             * Use the ALARM ringtone rather than the short
             * notification sound. This gives us a reliable audible
             * sound while the screen is locked.
             */
            Uri uri =
                    RingtoneManager.getDefaultUri(
                            RingtoneManager.TYPE_ALARM
                    );

            if (uri == null) {
                uri =
                        RingtoneManager.getDefaultUri(
                                RingtoneManager.TYPE_RINGTONE
                        );
            }

            if (uri == null) {
                uri =
                        RingtoneManager.getDefaultUri(
                                RingtoneManager.TYPE_NOTIFICATION
                        );
            }

            if (uri == null) {
                Log.w(
                        TAG,
                        "No event sound URI"
                );
                releaseWakeLock();
                return;
            }

            activeRingtone =
                    RingtoneManager.getRingtone(
                            context.getApplicationContext(),
                            uri
                    );

            if (activeRingtone == null) {
                releaseWakeLock();
                return;
            }

            /*
             * Loop deliberately. The receiver's own 7-second timer
             * always stops it. This prevents a 1-second notification
             * ringtone from ending before the user can hear it.
             */
            if (
                    Build.VERSION.SDK_INT
                            >= 28
            ) {
                activeRingtone.setLooping(
                        true
                );
            }

            activeRingtone.play();

            Log.i(
                    TAG,
                    "EVENT SOUND PLAYING"
            );

            final Context appContext =
                    context.getApplicationContext();

            final int durationMs =
                    ACTION_EVENT_TIME.equals(action)
                            ? EVENT_TIME_STOP_MS
                            : REMINDER_STOP_MS;

            new Thread(() -> {
                try {
                    Thread.sleep(
                            durationMs
                    );
                } catch (
                        InterruptedException ignored
                ) {
                }

                stopRingtoneOnly();
                releaseWakeLock();

                Log.i(
                        TAG,
                        "EVENT SOUND AUTO STOPPED"
                );
            }).start();

        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Event sound failed",
                    error
            );

            releaseWakeLock();
        }
    }

    private void stopRingtoneOnly() {
        try {
            if (activeRingtone != null) {
                activeRingtone.stop();
            }
        } catch (Exception error) {
            Log.e(
                    TAG,
                    "Ringtone stop failed",
                    error
            );
        }

        activeRingtone = null;
    }

    private void stopEventSound() {
        stopRingtoneOnly();
        releaseWakeLock();

        Log.i(
                TAG,
                "EVENT SOUND STOPPED"
        );
    }

    private String getStringExtra(
            Intent intent,
            String key,
            String fallback
    ) {
        if (intent == null) {
            return fallback;
        }

        String value =
                intent.getStringExtra(
                        key
                );

        if (value == null) {
            return fallback;
        }

        value = value.trim();

        return value.isEmpty()
                ? fallback
                : value;
    }
}