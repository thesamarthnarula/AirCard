import Foundation
import AppKit
import Vision
func fail(_ message: String) -> NSError { NSError(domain: "AirCard", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
func run() throws {
 guard CommandLine.arguments.count == 4 else { throw fail("Expected input, output and suffix") }
 let suffix = CommandLine.arguments[3]
 guard suffix.count == 4, suffix.allSatisfy({ $0.isNumber }), let im = NSImage(contentsOfFile: CommandLine.arguments[1]), let cg = im.cgImage(forProposedRect: nil, context: nil, hints: nil) else { throw fail("Invalid card image or suffix") }
 let w=cg.width, h=cg.height
 guard w >= 500 && w <= 2000 && h >= 300 && h <= 1300 else { throw fail("Unsupported image dimensions") }
 let space=CGColorSpace(name: CGColorSpace.sRGB)!, flags=CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
 var pixels=[UInt8](repeating:0,count:w*h*4)
 try pixels.withUnsafeMutableBytes { data in
  guard let c=CGContext(data:data.baseAddress,width:w,height:h,bitsPerComponent:8,bytesPerRow:w*4,space:space,bitmapInfo:flags) else { throw fail("Bitmap creation failed") }
  c.draw(cg,in:CGRect(x:0,y:0,width:w,height:h))
 }
 let x0=Int(Double(w)*0.075), x1=Int(Double(w)*0.30), y0=Int(Double(h)*0.845), y1=Int(Double(h)*0.925)
 var points=Set<Int>()
 for y in y0..<y1 { for x in x0..<x1 { let n=y*w+x, i=n*4; if pixels[i+3]>250 && min(pixels[i],min(pixels[i+1],pixels[i+2]))>=245 { points.insert(n) } } }
 var groups=[[Int]]()
 while let first=points.first {
  points.remove(first); var queue=[first], group=[first]
  while let n=queue.popLast() {
   let x=n%w,y=n/w
   for dy in -1...1 { for dx in -1...1 {
    let xx=x+dx,yy=y+dy
    if xx<x0 || xx>=x1 || yy<y0 || yy>=y1 { continue }
    let next=yy*w+xx
    if points.remove(next) != nil {queue.append(next);group.append(next)}
   } }
  }
  if group.count>=max(15,w*h/25000) { groups.append(group) }
 }
 groups.sort { ($0.map{$0%w}.min()!) < ($1.map{$0%w}.min()!) }
 guard groups.count==8 else { throw fail("Could not isolate four dots and four digits; no change made") }
 for (index,group) in groups.enumerated() {
  let xs=group.map{$0%w},ys=group.map{$0/w}, width=xs.max()!-xs.min()!+1,height=ys.max()!-ys.min()!+1
  let relative=Double(height)/Double(h)
  guard index<4 ? (relative>0.007 && relative<0.025 && abs(width-height)<5) : (relative>0.035 && relative<0.075) else { throw fail("Unsupported glyph layout") }
 }
 let digitPoints=groups.suffix(4).flatMap{$0}
 let left=digitPoints.map{$0%w}.min()!-4, top=digitPoints.map{$0/w}.min()!-4
 let ow=digitPoints.map{$0%w}.max()!-left+5, oh=digitPoints.map{$0/w}.max()!-top+5
 var verification=[UInt8](repeating:0,count:ow*oh*4)
 for n in 0..<(ow*oh) { verification[n*4+3]=255 }
 for n in digitPoints {
  let i=((n/w-top)*ow+(n%w-left))*4
  verification[i]=255;verification[i+1]=255;verification[i+2]=255
 }
 let verifyProvider=CGDataProvider(data:Data(verification) as CFData)!
 let verifyImage=CGImage(width:ow,height:oh,bitsPerComponent:8,bitsPerPixel:32,bytesPerRow:ow*4,space:space,bitmapInfo:CGBitmapInfo(rawValue:flags),provider:verifyProvider,decode:nil,shouldInterpolate:true,intent:.defaultIntent)!
 let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate;request.usesLanguageCorrection=false;request.recognitionLanguages=["en-US"]
 try VNImageRequestHandler(cgImage:verifyImage).perform([request])
 let candidates=(request.results ?? []).flatMap{$0.topCandidates(5)}
 guard candidates.contains(where:{$0.string.filter{$0.isNumber}==suffix && $0.confidence >= 0.5}) else { throw fail("Rendered number does not match card suffix") }
 var changed=0
 for group in groups { for n in group {
  let i=n*4, white=Double(min(pixels[i],min(pixels[i+1],pixels[i+2])))
  let coverage=min(1,max(0,(white-240)/15)),shade=UInt8((240*(1-coverage)).rounded())
  pixels[i]=shade;pixels[i+1]=shade;pixels[i+2]=shade;changed+=1
 } }
 let provider=CGDataProvider(data:Data(pixels) as CFData)!
 guard let patched=CGImage(width:w,height:h,bitsPerComponent:8,bitsPerPixel:32,bytesPerRow:w*4,space:space,bitmapInfo:CGBitmapInfo(rawValue:flags),provider:provider,decode:nil,shouldInterpolate:true,intent:.defaultIntent),let png=NSBitmapImageRep(cgImage:patched).representation(using:.png,properties:[:]) else { throw fail("PNG encoding failed") }
 try png.write(to:URL(fileURLWithPath:CommandLine.arguments[2]),options:.atomic)
 print("{\"ok\":true,\"changed_pixels\":\(changed)}")
}
do {try run()} catch {fputs(error.localizedDescription+"\n",stderr);exit(1)}
