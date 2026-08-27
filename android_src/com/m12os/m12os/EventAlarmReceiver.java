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
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

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
                22000
                        + Math.abs(
                        (
                                title
                                        + eventDateTime
                                        + action
                        ).hashCode()
                ) % 10000;

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
                    7000
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