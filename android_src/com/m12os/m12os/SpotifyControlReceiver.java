package com.m12os.m12os;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class SpotifyControlReceiver
        extends BroadcastReceiver {

    private static final String TAG =
            "M12SpotifyControl";

    public static final String ACTION_CONTROL =
            "com.m12os.m12os.SPOTIFY_CONTROL";

    public static final String EXTRA_COMMAND =
            "command";

    public static final String EXTRA_CLIENT_ID =
            "client_id";

    public static final String EXTRA_REDIRECT_URI =
            "redirect_uri";

    public static final String EXTRA_TRACK_ID =
            "track_id";

    @Override
    public void onReceive(
            Context context,
            Intent intent
    ) {
        if (intent == null) {
            return;
        }

        String action = intent.getAction();

        if (!ACTION_CONTROL.equals(action)) {
            return;
        }

        String command = safeText(
                intent.getStringExtra(
                        EXTRA_COMMAND
                )
        );

        String clientId = safeText(
                intent.getStringExtra(
                        EXTRA_CLIENT_ID
                )
        );

        String redirectUri = safeText(
                intent.getStringExtra(
                        EXTRA_REDIRECT_URI
                )
        );

        String trackId = safeText(
                intent.getStringExtra(
                        EXTRA_TRACK_ID
                )
        );

        if (
                clientId.isEmpty()
                || redirectUri.isEmpty()
        ) {
            Log.e(
                    TAG,
                    "Spotify configuration is missing"
            );
            return;
        }

        SpotifyAppRemoteBridge.configure(
                clientId,
                redirectUri
        );

        Log.i(
                TAG,
                "Spotify command received: "
                        + command
        );

        SpotifyAppRemoteBridge.control(
                context,
                command,
                trackId
        );
    }

    private static String safeText(
            String value
    ) {
        if (value == null) {
            return "";
        }

        return value.trim();
    }
}