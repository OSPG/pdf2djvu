cmake_minimum_required(VERSION 3.20)
project(pdf2djvu VERSION 0.9.19 LANGUAGES CXX)

include(GNUInstallDirs)
include(CheckCXXSymbolExists)
include(CheckIncludeFileCXX)

option(ENABLE_GRAPHICSMAGICK "Use GraphicsMagick for color quantization" ON)
option(ENABLE_XMP "Update XMP metadata using Exiv2 and UUID" ON)
option(ENABLE_NLS "Enable native language support" ON)
option(ENABLE_OPENMP "Enable parallel page rendering" ON)
option(ENABLE_HEAP_PROFILING "Enable heap profiling using gperftools" OFF)

find_package(PkgConfig REQUIRED)
pkg_check_modules(DJVULIBRE REQUIRED IMPORTED_TARGET ddjvuapi>=3.5.25)
pkg_check_modules(POPPLER REQUIRED IMPORTED_TARGET poppler>=26.0)
if(NOT CMAKE_CXX_STANDARD)
    set(CMAKE_CXX_STANDARD 20)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_REQUIRED_INCLUDES ${POPPLER_INCLUDE_DIRS})
check_include_file_cxx(GfxState.h HAVE_POPPLER_HEADERS)
unset(CMAKE_REQUIRED_INCLUDES)
if(NOT HAVE_POPPLER_HEADERS)
    message(FATAL_ERROR "Poppler's private (xpdf) development headers are required")
endif()

pkg_get_variable(djvulibre_prefix ddjvuapi exec_prefix)
set(DJVULIBRE_BINDIR "${djvulibre_prefix}/bin" CACHE PATH "Directory containing DjVuLibre command line tools")
foreach(tool bzz c44 cjb2 csepdjvu djvuextract djvumake djvused djvmcvt)
    if(NOT EXISTS "${DJVULIBRE_BINDIR}/${tool}${CMAKE_EXECUTABLE_SUFFIX}")
        message(FATAL_ERROR "Missing ${tool} in DJVULIBRE_BINDIR=${DJVULIBRE_BINDIR}")
    endif()
endforeach()

add_executable(pdf2djvu
    config.cc debug.cc djvu-outline.cc i18n.cc image-filter.cc main.cc
    pdf-backend.cc pdf-document-map.cc pdf-dpi.cc pdf-unicode.cc sexpr.cc
    string-format.cc string-printf.cc string-utils.cc sys-command-posix.cc
    sys-command-win32.cc sys-encoding.cc sys-time.cc sys-uuid.cc system.cc
    version.cc xmp.cc)
target_include_directories(pdf2djvu PRIVATE "${PROJECT_BINARY_DIR}")
target_link_libraries(pdf2djvu PRIVATE PkgConfig::DJVULIBRE PkgConfig::POPPLER)
target_compile_definitions(pdf2djvu PRIVATE _FILE_OFFSET_BITS=64)
find_package(Iconv REQUIRED)
target_link_libraries(pdf2djvu PRIVATE Iconv::Iconv)
check_cxx_symbol_exists(timegm "time.h" HAVE_TIMEGM)

if(WIN32)
    enable_language(RC)
    target_sources(pdf2djvu PRIVATE win32-version.rc)
    target_compile_definitions(pdf2djvu PRIVATE WIN32=1)
    if(MINGW)
        set(USE_MINGW_ANSI_STDIO 1)
    endif()
endif()
if(ENABLE_OPENMP)
    find_package(OpenMP QUIET COMPONENTS CXX)
    if(OpenMP_CXX_FOUND)
        target_link_libraries(pdf2djvu PRIVATE OpenMP::OpenMP_CXX)
    endif()
endif()
if(ENABLE_GRAPHICSMAGICK)
    pkg_check_modules(GRAPHICSMAGICK QUIET IMPORTED_TARGET GraphicsMagick++)
    if(GRAPHICSMAGICK_FOUND)
        set(HAVE_GRAPHICSMAGICK 1)
        target_link_libraries(pdf2djvu PRIVATE PkgConfig::GRAPHICSMAGICK)
    endif()
endif()
if(ENABLE_XMP)
    pkg_check_modules(EXIV2 QUIET IMPORTED_TARGET exiv2>=0.21)
    if(EXIV2_FOUND)
        if(WIN32)
            target_link_libraries(pdf2djvu PRIVATE rpcrt4)
            set(HAVE_XMP 1)
        else()
            check_cxx_symbol_exists(uuid_create "stdint.h;uuid.h" HAVE_DCE_UUID)
            if(HAVE_DCE_UUID)
                set(HAVE_XMP 1)
            else()
                pkg_check_modules(LIBUUID QUIET IMPORTED_TARGET uuid)
                if(LIBUUID_FOUND)
                    set(HAVE_LIBUUID 1)
                    set(HAVE_XMP 1)
                    target_link_libraries(pdf2djvu PRIVATE PkgConfig::LIBUUID)
                endif()
            endif()
        endif()
    endif()
    if(HAVE_XMP)
        target_link_libraries(pdf2djvu PRIVATE PkgConfig::EXIV2)
    endif()
endif()
if(ENABLE_NLS)
    find_package(Intl QUIET)
    if(Intl_FOUND)
        target_link_libraries(pdf2djvu PRIVATE Intl::Intl)
        set(HAVE_NLS 1)
    endif()
endif()
if(ENABLE_HEAP_PROFILING)
    find_library(TCMALLOC_LIBRARY NAMES tcmalloc REQUIRED)
    find_path(TCMALLOC_INCLUDE_DIR gperftools/heap-profiler.h REQUIRED)
    target_link_libraries(pdf2djvu PRIVATE "${TCMALLOC_LIBRARY}")
    target_include_directories(pdf2djvu PRIVATE "${TCMALLOC_INCLUDE_DIR}")
    set(USE_HEAP_PROFILING 1)
endif()

string(REPLACE "." ";" poppler_version_parts "${POPPLER_VERSION}")
list(GET poppler_version_parts 0 poppler_major)
list(GET poppler_version_parts 1 poppler_minor)
list(GET poppler_version_parts 2 poppler_patch)
foreach(component major minor patch)
    string(REGEX REPLACE "^0+([0-9])" "\\1" poppler_${component} "${poppler_${component}}")
endforeach()
math(EXPR POPPLER_VERSION_NUMBER "${poppler_major} * 10000 + ${poppler_minor} * 100 + ${poppler_patch}")
# Poppler defines POPPLER_VERSION as a string; keep our numeric checks separate.
file(CONFIGURE OUTPUT "${PROJECT_BINARY_DIR}/autoconf.hh" CONTENT [=[
#ifndef PDF2DJVU_AUTOCONF_HH
#define PDF2DJVU_AUTOCONF_HH
#define PACKAGE_NAME "pdf2djvu"
#define PACKAGE_VERSION "@PROJECT_VERSION@"
#define PACKAGE_STRING "pdf2djvu @PROJECT_VERSION@"
#define PACKAGE_BUGREPORT "https://github.com/jwilk/pdf2djvu/issues"
#define DJVULIBRE_VERSION_STRING "@DJVULIBRE_VERSION@"
#define POPPLER_VERSION_STRING "@POPPLER_VERSION@"
#define POPPLER_VERSION_NUMBER @POPPLER_VERSION_NUMBER@
#cmakedefine HAVE_TIMEGM 1
#cmakedefine HAVE_GRAPHICSMAGICK 1
#cmakedefine HAVE_XMP 1
#cmakedefine HAVE_LIBUUID 1
#cmakedefine HAVE_DCE_UUID 1
#cmakedefine USE_MINGW_ANSI_STDIO 1
#cmakedefine USE_HEAP_PROFILING 1
#cmakedefine HAVE_NLS 1
#ifdef HAVE_NLS
#define ENABLE_NLS 1
#endif
#endif
]=] @ONLY)
set(localedir "${CMAKE_INSTALL_FULL_LOCALEDIR}")
set(djvulibre_bindir "${DJVULIBRE_BINDIR}")
foreach(path localedir djvulibre_bindir)
    string(REPLACE "\\" "\\\\" ${path} "${${path}}")
    string(REPLACE "\"" "\\\"" ${path} "${${path}}")
endforeach()
file(CONFIGURE OUTPUT "${PROJECT_BINARY_DIR}/paths.hh" CONTENT [=[
#ifndef PDF2DJVU_PATHS
#define PDF2DJVU_PATHS
namespace paths
{
    static const char localedir[] = "@localedir@";
    static const char djvulibre_bindir[] = "@djvulibre_bindir@";
}
#endif
]=] @ONLY)
install(TARGETS pdf2djvu RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")

# Install documentation and catalogs already built by the existing tools.
file(GLOB manpages "doc/*.1" "doc/po/*.1")
foreach(manpage IN LISTS manpages)
    get_filename_component(name "${manpage}" NAME)
    set(lang "")
    if(name MATCHES "^pdf2djvu[.](.+)[.]1$")
        set(lang "${CMAKE_MATCH_1}/")
    endif()
    install(FILES "${manpage}" DESTINATION "${CMAKE_INSTALL_MANDIR}/${lang}man1" RENAME pdf2djvu.1)
endforeach()
if(HAVE_NLS)
    file(GLOB catalogs "po/*.mo")
    foreach(catalog IN LISTS catalogs)
        get_filename_component(lang "${catalog}" NAME_WE)
        install(FILES "${catalog}" DESTINATION "${CMAKE_INSTALL_LOCALEDIR}/${lang}/LC_MESSAGES" RENAME pdf2djvu.mo)
    endforeach()
endif()
message(STATUS "Optional features: GraphicsMagick=${HAVE_GRAPHICSMAGICK}; XMP=${HAVE_XMP}; NLS=${HAVE_NLS}; OpenMP=${OpenMP_CXX_FOUND}")
