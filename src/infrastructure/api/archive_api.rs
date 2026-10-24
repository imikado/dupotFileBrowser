//! Archives written and read in-process (zip, tar, gzip, bzip2, xz crates),
//! so it works whatever is installed in the sandbox. RAR, a proprietary
//! format, is extracted by a host tool.

use std::fs::{self, File};
use std::io::{self, BufWriter, Seek, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::time::Duration;

use crate::domain::contract::archive_repository::ArchiveRepository;
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::archive::{
    ArchiveFormat, ArchiveKind, RAR_TOOLS, archive_kind, rar_extract_argv,
};
use crate::domain::shared::path::file_name;
use crate::infrastructure::service::host_command_service;
use crate::infrastructure::service::i18n_service::tr;

const RAR_TIMEOUT: Duration = Duration::from_secs(600);

#[derive(Clone, Copy, Debug, Default)]
pub struct ArchiveApi;

fn write_tar<W: Write>(writer: W, source: &Path) -> io::Result<W> {
    let mut builder = tar::Builder::new(writer);
    builder.follow_symlinks(false);
    let name = file_name(source);
    if fs::symlink_metadata(source)?.is_dir() {
        builder.append_dir_all(&name, source)?;
    } else {
        builder.append_path_with_name(source, &name)?;
    }
    builder.into_inner()
}

fn write_zip<W: Write + Seek>(writer: W, source: &Path) -> DomainResult<()> {
    let mut zip = zip::ZipWriter::new(writer);
    add_to_zip(&mut zip, source, &file_name(source))?;
    zip.finish()?.flush()?;
    Ok(())
}

fn add_to_zip<W: Write + Seek>(
    zip: &mut zip::ZipWriter<W>,
    path: &Path,
    name: &str,
) -> DomainResult<()> {
    let Ok(metadata) = fs::metadata(path) else {
        // A dangling symlink has nothing to store; anything else is an error.
        return match fs::symlink_metadata(path) {
            Ok(_) => Ok(()),
            Err(error) => Err(error.into()),
        };
    };
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated)
        .unix_permissions(metadata.permissions().mode() & 0o7777);
    if metadata.is_dir() {
        zip.add_directory(format!("{name}/"), options)?;
        // A symlink to a folder is stored as an empty folder, not followed.
        if fs::symlink_metadata(path)?.file_type().is_symlink() {
            return Ok(());
        }
        let mut children: Vec<_> = fs::read_dir(path)?.flatten().collect();
        children.sort_by_key(|entry| entry.file_name());
        for child in children {
            let child_name = format!("{name}/{}", child.file_name().to_string_lossy());
            add_to_zip(zip, &child.path(), &child_name)?;
        }
    } else {
        zip.start_file(name, options)?;
        io::copy(&mut File::open(path)?, zip)?;
    }
    Ok(())
}

fn compress_into(file: File, source: &Path, format: ArchiveFormat) -> DomainResult<()> {
    let writer = BufWriter::new(file);
    match format {
        ArchiveFormat::Zip => write_zip(writer, source)?,
        ArchiveFormat::Tar => {
            write_tar(writer, source)?.flush()?;
        }
        ArchiveFormat::TarGz => {
            let encoder = flate2::write::GzEncoder::new(writer, flate2::Compression::default());
            write_tar(encoder, source)?.finish()?.flush()?;
        }
        ArchiveFormat::TarBz2 => {
            let encoder = bzip2::write::BzEncoder::new(writer, bzip2::Compression::default());
            write_tar(encoder, source)?.finish()?.flush()?;
        }
        ArchiveFormat::TarXz => {
            let encoder = xz2::write::XzEncoder::new(writer, 6);
            write_tar(encoder, source)?.finish()?.flush()?;
        }
    }
    Ok(())
}

fn unpack_tar(reader: impl io::Read, destination_dir: &Path) -> DomainResult<()> {
    let mut archive = tar::Archive::new(reader);
    archive.set_preserve_permissions(true);
    archive.unpack(destination_dir)?;
    Ok(())
}

fn extract_rar(source: &Path, destination_dir: &Path) -> DomainResult<()> {
    let source = source.to_string_lossy();
    let destination = destination_dir.to_string_lossy();
    let mut last_error = None;
    for tool in RAR_TOOLS {
        if !host_command_service::command_exists(tool) {
            continue;
        }
        match host_command_service::run_capture(
            &rar_extract_argv(tool, &source, &destination),
            RAR_TIMEOUT,
        ) {
            Ok(_) => return Ok(()),
            Err(error) => last_error = Some(error),
        }
    }
    Err(DomainError::new(last_error.unwrap_or_else(|| {
        tr("No RAR-capable tool was found on this system (tried unrar, 7z, unar, bsdtar — install one of these to extract .rar archives).")
    })))
}

impl ArchiveRepository for ArchiveApi {
    fn compress(
        &self,
        source: &Path,
        destination: &Path,
        format: ArchiveFormat,
    ) -> DomainResult<()> {
        let file = File::create(destination)?;
        let result = compress_into(file, source, format);
        if result.is_err() {
            let _ = fs::remove_file(destination);
        }
        result
    }

    fn extract(&self, source: &Path, destination_dir: &Path) -> DomainResult<()> {
        let kind = archive_kind(&file_name(source)).ok_or_else(|| {
            DomainError::new(format!("Unknown archive format: {}", source.display()))
        })?;
        let created = !destination_dir.exists();
        fs::create_dir_all(destination_dir)?;
        let result = unpack(kind, source, destination_dir);
        // A failed extraction must not leave a half-filled folder behind.
        if result.is_err() && created {
            let _ = fs::remove_dir_all(destination_dir);
        }
        result
    }
}

fn unpack(kind: ArchiveKind, source: &Path, destination_dir: &Path) -> DomainResult<()> {
    let open = || File::open(source).map(io::BufReader::new);
    match kind {
        ArchiveKind::Rar => extract_rar(source, destination_dir),
        ArchiveKind::Format(ArchiveFormat::Zip) => {
            zip::ZipArchive::new(File::open(source)?)?.extract(destination_dir)?;
            Ok(())
        }
        ArchiveKind::Format(ArchiveFormat::Tar) => unpack_tar(open()?, destination_dir),
        ArchiveKind::Format(ArchiveFormat::TarGz) => {
            unpack_tar(flate2::read::GzDecoder::new(open()?), destination_dir)
        }
        ArchiveKind::Format(ArchiveFormat::TarBz2) => {
            unpack_tar(bzip2::read::BzDecoder::new(open()?), destination_dir)
        }
        ArchiveKind::Format(ArchiveFormat::TarXz) => {
            unpack_tar(xz2::read::XzDecoder::new(open()?), destination_dir)
        }
    }
}
