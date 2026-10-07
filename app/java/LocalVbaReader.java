import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.*;
import org.apache.poi.poifs.filesystem.*;
import org.apache.poi.poifs.macros.VBAMacroReader;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;

/** Local binary reader only. No Office automation, network or macro execution. */
public class LocalVbaReader {
  static String quote(String s) {
    if(s==null)return "null";
    StringBuilder b=new StringBuilder("\"");
    for(char c:s.toCharArray()) {
      if(c=='"'||c=='\\')b.append('\\').append(c);
      else if(c<32)b.append(String.format("\\u%04x",(int)c)); else b.append(c);
    }
    return b.append('"').toString();
  }
  static byte[] stream(DirectoryNode d,String name)throws IOException {
    try(DocumentInputStream in=d.createDocumentInputStream(name)){return in.readNBytes(1048577);}
  }
  static DirectoryNode project(DirectoryNode d) {
    if(d.hasEntry("PROJECT"))return d;
    for(Entry e:d)if(e.isDirectoryEntry()){DirectoryNode r=project((DirectoryNode)e);if(r!=null)return r;}
    return null;
  }
  static boolean hasVba(DirectoryNode d) {
    if(d.hasEntry("VBA"))return true;
    for(Entry e:d)if(e.isDirectoryEntry()&&hasVba((DirectoryNode)e))return true;
    return false;
  }
  static void extract(Path input,Path output)throws Exception {
    Files.createDirectories(output);
    String status="NO_VBA";boolean protection=false;Map<String,String> types=new HashMap<>();
    List<String> json=new ArrayList<>(),sheets=new ArrayList<>();
    try(POIFSFileSystem fs=new POIFSFileSystem(input.toFile(),true)) {
      DirectoryNode root=fs.getRoot();
      if(root.hasEntry("EncryptedPackage")||root.hasEntry("EncryptionInfo"))status="ENCRYPTED";
      else {
        DirectoryNode pr=project(root);
        if(pr!=null) {
          String props=new String(stream(pr,"PROJECT"),Charset.forName("windows-31j"));
          for(String line:props.split("\\r?\\n")) {
            int pos=line.indexOf('=');if(pos<0)continue;
            String key=line.substring(0,pos),value=line.substring(pos+1).split("/")[0];
            if(key.equals("Document")||key.equals("Module")||key.equals("Class")||key.equals("BaseClass"))types.put(value,key);
            if(key.equals("DPB")||key.equals("CMG"))protection=true;
          }
        }
        if(root.hasEntry("Workbook")||root.hasEntry("Book")) {
          try(HSSFWorkbook wb=new HSSFWorkbook(fs,false)) {
            for(int i=0;i<wb.getNumberOfSheets();i++)sheets.add(quote(wb.getSheetName(i)));
          } catch(Exception ignored) {sheets.clear();}
        }
        if(hasVba(root)) {
          try(VBAMacroReader reader=new VBAMacroReader(input.toFile())) {
            Map<String,org.apache.poi.poifs.macros.Module> modules=reader.readMacroModules();
            if(modules.size()>1000)throw new IOException("MODULE_LIMIT");
            int n=0;
            for(String name:new TreeSet<>(modules.keySet())) {
              org.apache.poi.poifs.macros.Module module=modules.get(name);
              String content=module.getContent();if(content==null)throw new IOException("SOURCE_UNAVAILABLE");
              if(content.length()>16000000)throw new IOException("SOURCE_LIMIT");
              String file=String.format("module_%04d.txt",++n);
              Files.writeString(output.resolve(file),content,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
              String type=types.get(name);
              if(type==null)type=module.geModuleType()==null?"Unknown":module.geModuleType().name();
              json.add("{\"name\":"+quote(name)+",\"projectType\":"+quote(type)+",\"file\":"+quote(file)+"}");
            }
            status=modules.isEmpty()?"VBA_UNREADABLE":"SUCCESS";
          }
        }
      }
    }
    String result="{\"status\":"+quote(status)+",\"protectionMetadata\":"+protection+",\"sheets\":["+String.join(",",sheets)+"],\"modules\":["+String.join(",",json)+"]}";
    Files.writeString(output.resolve("index.json"),result,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW);
  }
  static void add(DirectoryEntry root,Path source)throws IOException {
    DirectoryEntry vba=root.createDirectory("VBA");
    try(var files=Files.list(source.resolve("VBA"))) {
      for(Path p:files.sorted().toList())try(InputStream in=Files.newInputStream(p)){vba.createDocument(p.getFileName().toString(),in);}
    }
    try(InputStream in=Files.newInputStream(source.resolve("PROJECT"))){root.createDocument("PROJECT",in);}
    if(Files.exists(source.resolve("PROJECTwm")))try(InputStream in=Files.newInputStream(source.resolve("PROJECTwm"))){root.createDocument("PROJECTwm",in);}
  }
  static void fixture(Path source,Path output,String type)throws Exception {
    try(POIFSFileSystem fs=new POIFSFileSystem()) {
      if(type.equals("encrypted")) {
        fs.createDocument(new ByteArrayInputStream(new byte[]{1,2,3,4}),"EncryptionInfo");
        fs.createDocument(new ByteArrayInputStream(new byte[]{1,2,3,4}),"EncryptedPackage");
      } else if(type.equals("xls")) {
        byte[] workbook;
        try(HSSFWorkbook wb=new HSSFWorkbook();ByteArrayOutputStream out=new ByteArrayOutputStream()){
          wb.createSheet("Sample").createRow(0).createCell(0).setCellValue("Synthetic only");wb.write(out);workbook=out.toByteArray();
        }
        try(POIFSFileSystem other=new POIFSFileSystem(new ByteArrayInputStream(workbook))) {
          fs.createDocument(new ByteArrayInputStream(stream(other.getRoot(),"Workbook")),"Workbook");
        }
        add(fs.getRoot().createDirectory("_VBA_PROJECT_CUR"),source);
      } else add(fs.getRoot(),source);
      try(OutputStream out=Files.newOutputStream(output,StandardOpenOption.CREATE_NEW)){fs.writeFilesystem(out);}
    }
  }
  public static void main(String[] args) {
    try {
      if(args.length==4&&args[0].equals("fixture"))fixture(Path.of(args[1]),Path.of(args[2]),args[3]);
      else if(args.length==3&&args[0].equals("extract"))extract(Path.of(args[1]),Path.of(args[2]));
      else throw new IllegalArgumentException();
      System.out.println("LOCAL_READER_OK");
    }catch(Exception ex){System.err.println("LOCAL_READER_FAILED:"+ex.getClass().getSimpleName());System.exit(2);}
  }
}
