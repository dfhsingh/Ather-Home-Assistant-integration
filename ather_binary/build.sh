#!/bin/bash

# 1. Clean old artifacts to prevent library conflicts
echo "Cleaning old build artifacts..."
rm -rf core/target

# 2. Ensure necessary targets are installed
echo "Checking Rust targets..."
INSTALLED_TARGETS=$(rustup target list --installed)
for TARGET in aarch64-unknown-linux-musl x86_64-unknown-linux-musl; do
    if ! echo "$INSTALLED_TARGETS" | grep -q "$TARGET"; then
        echo "Installing target $TARGET..."
        rustup target add "$TARGET"
    fi
done

# 3. Create binary directory structure
mkdir -p bin/linux-aarch64 bin/linux-x86_64

build_target() {
    TARGET=$1
    OUTPUT_DIR=$2
    echo "------------------------------------------------"
    echo "Building for $TARGET..."
    
    (
        cd core || exit 1
        if command -v maturin &> /dev/null; then
            # Use --zig for ALL targets when cross-compiling to ensure correct headers/linkers
            if ! command -v zig &> /dev/null; then
                echo "Error: zig not found. Please install zig (e.g., brew install zig or pacman -S zig)"
                exit 1
            fi
            
            if [[ $TARGET == *"linux"* ]]; then
                maturin build --release --target "$TARGET" --compatibility linux --zig
            else
                # For macOS targets, zig is also excellent at cross-compiling from Linux
                maturin build --release --target "$TARGET" --zig
            fi
        else
            echo "Error: maturin not found. Run: pip3 install maturin"
            exit 1
        fi
    )

    # Find the built .so or .dylib file
    BINARY="core/target/$TARGET/release/libather_core.so"
    DYLIB="core/target/$TARGET/release/libather_core.dylib"

    if [ -f "$BINARY" ]; then
        cp "$BINARY" "bin/$OUTPUT_DIR/ather_core.so"
        echo "✅ Success: bin/$OUTPUT_DIR/ather_core.so"
    elif [ -f "$DYLIB" ]; then
        cp "$DYLIB" "bin/$OUTPUT_DIR/ather_core.so"
        echo "✅ Success: bin/$OUTPUT_DIR/ather_core.so (from dylib)"
    else
        # Fallback to searching if not found in standard location
        FIND_SO=$(find core/target/$TARGET/release -name "libather_core.so" | head -n 1)
        if [ -n "$FIND_SO" ]; then
            cp "$FIND_SO" "bin/$OUTPUT_DIR/ather_core.so"
            echo "✅ Success: bin/$OUTPUT_DIR/ather_core.so (found via search)"
        else
             echo "❌ Error: Build for $TARGET failed or binary not found."
        fi
    fi
}

# Build for Linux platforms
build_target "aarch64-unknown-linux-musl" "linux-aarch64"
build_target "x86_64-unknown-linux-musl" "linux-x86_64"

echo "------------------------------------------------"
echo "All builds completed. Your binaries are ready in the bin/ directory."

# Cleanup huge target directory to save space
echo "Cleaning up build artifacts..."
rm -rf core/target
echo "Done."
