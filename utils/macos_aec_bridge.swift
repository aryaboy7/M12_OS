import Foundation

import AVFoundation

final class M12MacAECBridge {

    private let engine = AVAudioEngine()

    private let player = AVAudioPlayerNode()

    private let stdinHandle = FileHandle.standardInput

    private let stdoutHandle = FileHandle.standardOutput

    private let stderrHandle = FileHandle.standardError

    private let playbackQueue = DispatchQueue(

        label: "com.m12os.mac-aec.playback"

    )

    private let stdoutQueue = DispatchQueue(

        label: "com.m12os.mac-aec.stdout"

    )

    private let transportSampleRate: Double = 24_000.0

    private var running = true

    private var micCallbackCount: Int = 0

    private var playbackChunkCount: Int = 0

    private var lastMicLogTime = Date.distantPast

    private var lastPlaybackLogTime = Date.distantPast

    private func log(_ text: String) {

        guard let data = "[M12MacAEC] \(text)\n".data(using: .utf8) else {

            return

        }

        stderrHandle.write(data)

    }

    func start() throws {

        let input = engine.inputNode

        let output = engine.outputNode

        try input.setVoiceProcessingEnabled(true)

        try output.setVoiceProcessingEnabled(true)

        // Explicitly keep Apple's microphone voice-processing path active.

        // Do not allow the Voice Processing I/O unit to bypass AEC.

        input.isVoiceProcessingBypassed = false

        input.isVoiceProcessingAGCEnabled = true

        guard input.isVoiceProcessingEnabled,

              output.isVoiceProcessingEnabled else {

            throw NSError(

                domain: "M12MacAEC",

                code: 1,

                userInfo: [

                    NSLocalizedDescriptionKey:

                        "Apple Voice Processing did not activate."

                ]

            )

        }

        let inputFormat = input.outputFormat(forBus: 0)

        let outputFormat = output.inputFormat(forBus: 0)

        guard inputFormat.sampleRate > 0,

              inputFormat.channelCount > 0 else {

            throw NSError(

                domain: "M12MacAEC",

                code: 2,

                userInfo: [

                    NSLocalizedDescriptionKey:

                        "Invalid Voice Processing input format: \(inputFormat)"

                ]

            )

        }

        guard outputFormat.sampleRate > 0,

              outputFormat.channelCount > 0 else {

            throw NSError(

                domain: "M12MacAEC",

                code: 3,

                userInfo: [

                    NSLocalizedDescriptionKey:

                        "Invalid Voice Processing output format: \(outputFormat)"

                ]

            )

        }

        engine.attach(player)

        // Do not touch mainMixerNode here. On the tested Mac that created a

        // 44.1 kHz mixer path while Voice Processing I/O was 48 kHz, causing

        // Core Audio initialization error -10875.

        engine.connect(

            player,

            to: output,

            format: outputFormat

        )

        // Ask for about 20 ms of microphone audio at the actual hardware/

        // Voice Processing sample rate. macOS may provide 16 kHz, 48 kHz,

        // or another valid rate depending on the selected device/session.

        let tapFrames = max(

            160,

            Int((inputFormat.sampleRate * 0.020).rounded())

        )

        input.installTap(

            onBus: 0,

            bufferSize: AVAudioFrameCount(tapFrames),

            format: inputFormat

        ) { [weak self] buffer, _ in

            self?.handleMicrophone(buffer)

        }

        engine.prepare()

        try engine.start()

        player.play()

        log("input format: \(inputFormat)")

        log("output format: \(outputFormat)")

        log(

            "ACTIVE voiceProcessing=true "

            + "bypassed=\(input.isVoiceProcessingBypassed) "

            + "agc=\(input.isVoiceProcessingAGCEnabled) "

            + "input=\(Int(inputFormat.sampleRate))Hz "

            + "output=\(Int(outputFormat.sampleRate))Hz "

            + "transport=24000Hz/1ch/S16LE"

        )

        startPlaybackReader(outputFormat: outputFormat)

    }

    private func handleMicrophone(_ buffer: AVAudioPCMBuffer) {

        guard running,

              let channels = buffer.floatChannelData,

              buffer.format.channelCount > 0 else {

            return

        }

        let source = channels[0]

        let inputFrames = Int(buffer.frameLength)

        let inputRate = buffer.format.sampleRate

        guard inputFrames > 0,

              inputRate > 0 else {

            return

        }

        micCallbackCount += 1

        let now = Date()

        if now.timeIntervalSince(lastMicLogTime) >= 1.0 {

            var sumSquares: Float = 0.0

            for i in 0..<inputFrames {

                let value = source[i]

                sumSquares += value * value

            }

            let rms = sqrt(

                sumSquares / Float(inputFrames)

            )

            let rmsText = String(

                format: "%.5f",

                rms

            )

            log(

                "MIC active callbacks=\(micCallbackCount) "

                + "frames=\(inputFrames) "

                + "rate=\(Int(inputRate))Hz "

                + "rms=\(rmsText)"

            )

            lastMicLogTime = now

        }

        let outputFrames = max(

            1,

            Int(

                (

                    Double(inputFrames)

                    * transportSampleRate

                    / inputRate

                ).rounded()

            )

        )

        var pcm = [Int16](

            repeating: 0,

            count: outputFrames

        )

        // Resample the actual Voice Processing input rate to M12's fixed

        // 24 kHz mono transport. Linear interpolation is sufficient here

        // because the transport is speech-only and Apple AEC/AGC has already

        // processed the microphone signal.

        let scale = inputRate / transportSampleRate

        for i in 0..<outputFrames {

            let sourcePosition = Double(i) * scale

            let leftIndex = min(

                Int(sourcePosition),

                inputFrames - 1

            )

            let rightIndex = min(

                leftIndex + 1,

                inputFrames - 1

            )

            let fraction = Float(

                sourcePosition - Double(leftIndex)

            )

            let sample = (

                source[leftIndex] * (1.0 - fraction)

                + source[rightIndex] * fraction

            )

            let clipped = max(

                -1.0,

                min(1.0, sample)

            )

            let scaled: Float

            if clipped >= 0 {

                scaled = clipped * 32767.0

            } else {

                scaled = clipped * 32768.0

            }

            pcm[i] = Int16(

                scaled.rounded()

            )

        }

        let data = pcm.withUnsafeBytes {

            Data($0)

        }

        stdoutQueue.async { [weak self] in

            guard let self = self,

                  self.running else {

                return

            }

            self.stdoutHandle.write(data)

        }

    }

    private func startPlaybackReader(

        outputFormat: AVAudioFormat

    ) {

        playbackQueue.async { [weak self] in

            guard let self = self else {

                return

            }

            var pending = Data()

            while self.running {

                autoreleasepool {

                    do {

                        guard let chunk = try self.stdinHandle.read(

                            upToCount: 4096

                        ) else {

                            self.running = false

                            return

                        }

                        if chunk.isEmpty {

                            self.running = false

                            return

                        }

                        pending.append(chunk)

                        let usable = pending.count & ~1

                        guard usable > 0 else {

                            return

                        }

                        let audio = Data(

                            pending.prefix(usable)

                        )

                        pending.removeFirst(usable)

                        self.playbackChunkCount += 1

                        let now = Date()

                        if now.timeIntervalSince(

                            self.lastPlaybackLogTime

                        ) >= 1.0 {

                            self.log(

                                "PLAYBACK active chunks=\(self.playbackChunkCount) "

                                + "bytes=\(audio.count) "

                                + "output=\(Int(outputFormat.sampleRate))Hz"

                            )

                            self.lastPlaybackLogTime = now

                        }

                        self.schedulePlayback(

                            audio,

                            outputFormat: outputFormat

                        )

                    } catch {

                        self.log(

                            "stdin read failed: \(error)"

                        )

                        self.running = false

                    }

                }

            }

        }

    }

    private func schedulePlayback(

        _ data: Data,

        outputFormat: AVAudioFormat

    ) {

        let inputFrames = data.count / 2

        guard inputFrames > 0,

              outputFormat.sampleRate > 0,

              outputFormat.channelCount > 0 else {

            return

        }

        // M12 transport is always 24 kHz mono. Resample it to the actual

        // Voice Processing output rate that macOS selected.

        let outputFrames = max(

            1,

            Int(

                (

                    Double(inputFrames)

                    * outputFormat.sampleRate

                    / transportSampleRate

                ).rounded()

            )

        )

        guard let buffer = AVAudioPCMBuffer(

            pcmFormat: outputFormat,

            frameCapacity: AVAudioFrameCount(outputFrames)

        ) else {

            return

        }

        buffer.frameLength = AVAudioFrameCount(

            outputFrames

        )

        guard let channels = buffer.floatChannelData else {

            return

        }

        data.withUnsafeBytes { raw in

            let source = raw.bindMemory(

                to: Int16.self

            )

            let scale = (

                transportSampleRate

                / outputFormat.sampleRate

            )

            for i in 0..<outputFrames {

                let sourcePosition = Double(i) * scale

                let leftIndex = min(

                    Int(sourcePosition),

                    inputFrames - 1

                )

                let rightIndex = min(

                    leftIndex + 1,

                    inputFrames - 1

                )

                let fraction = Float(

                    sourcePosition - Double(leftIndex)

                )

                let leftSample = Float(

                    Int16(

                        littleEndian: source[leftIndex]

                    )

                ) / 32768.0

                let rightSample = Float(

                    Int16(

                        littleEndian: source[rightIndex]

                    )

                ) / 32768.0

                let value = (

                    leftSample * (1.0 - fraction)

                    + rightSample * fraction

                )

                for ch in 0..<Int(

                    outputFormat.channelCount

                ) {

                    channels[ch][i] = value

                }

            }

        }

        player.scheduleBuffer(

            buffer,

            completionHandler: nil

        )

    }

    func run() {

        while running {

            RunLoop.current.run(

                mode: .default,

                before: Date(

                    timeIntervalSinceNow: 0.1

                )

            )

        }

        shutdown()

    }

    private func shutdown() {

        running = false

        engine.inputNode.removeTap(

            onBus: 0

        )

        if player.isPlaying {

            player.stop()

        }

        engine.stop()

        log("STOPPED")

    }

}

do {

    let bridge = M12MacAECBridge()

    try bridge.start()

    bridge.run()

} catch {

    let text = "[M12MacAEC] FAILED: \(error)\n"

    if let data = text.data(

        using: .utf8

    ) {

        FileHandle.standardError.write(data)

    }

    exit(1)

}
