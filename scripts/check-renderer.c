/* SPDX-License-Identifier: MIT */
/* Create a tiny off-screen context to identify the actual Mesa renderer. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    EGLDisplay display = eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA,
                                               EGL_DEFAULT_DISPLAY, NULL);
    EGLConfig config;
    EGLint count;
    EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                           EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_NONE};
    EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    EGLint surface_attributes[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE};
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL)) {
        fprintf(stderr, "EGL initialization failed: 0x%x\n", eglGetError());
        return 1;
    }
    if (!eglBindAPI(EGL_OPENGL_ES_API) ||
        !eglChooseConfig(display, attributes, &config, 1, &count) || count != 1) {
        fprintf(stderr, "No usable EGL configuration: 0x%x\n", eglGetError());
        eglTerminate(display);
        return 1;
    }
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT,
                                         context_attributes);
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attributes);
    if (context == EGL_NO_CONTEXT || surface == EGL_NO_SURFACE ||
        !eglMakeCurrent(display, surface, surface, context)) {
        fprintf(stderr, "Off-screen context failed: 0x%x\n", eglGetError());
        eglTerminate(display);
        return 1;
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    const char *vendor = (const char *)glGetString(GL_VENDOR);
    const char *version = (const char *)glGetString(GL_VERSION);
    printf("Renderer: %s\nVendor: %s\nVersion: %s\n",
           renderer ? renderer : "unknown", vendor ? vendor : "unknown",
           version ? version : "unknown");
    int result = !renderer || !strstr(renderer, "Apple");
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroySurface(display, surface);
    eglDestroyContext(display, context);
    eglTerminate(display);
    return result;
}
