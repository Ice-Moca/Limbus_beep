import sys
p = '/home/c/pager-android/.buildozer/android/platform/build-arm64-v8a_armeabi-v7a/dists/pager/build.gradle'
with open(p) as f:
    t = f.read()

# Replace the whole configurations block with a proper one
# Find and replace the broken block
import re
# Remove old configurations block
t = re.sub(r'configurations\.configureEach \{.*?\n\}', '', t, flags=re.DOTALL)

# Add proper fix at end
fix = """
configurations.configureEach {
    resolutionStrategy.eachDependency { details ->
        if (details.requested.group == 'org.jetbrains.kotlin') {
            if (details.requested.name.startsWith('kotlin-stdlib')) {
                details.useVersion '1.8.22'
                details.because 'align kotlin-stdlib versions to avoid duplicates'
            }
        }
    }
}
"""
t = t.rstrip() + "\n" + fix
with open(p, 'w') as f:
    f.write(t)
print('DONE')
