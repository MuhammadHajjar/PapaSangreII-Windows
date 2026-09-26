# Use this script to generate playlists for Papa Sangre 2
# Call that script with the name path of the folder you want to transform as a playlist, and the name you want to give to your playlist 
# example : python generate_playlist.py footsteps/Submarine/ _footsteps_submarine
# create some empty files named xxx.subplaylist if you want to import sub playlists in the one you're creating


import os
import sys

output = '(playlist\n' 
output += '\t(name "' + sys.argv[2] + '")\n'
output += '\t(repeat none)\n\n'


for root, dirs, files in os.walk('./'):
	for name in files:       
		filepath = os.path.join(root, name)
		if filepath.startswith('./' + sys.argv[1] +'/') :
			items = filepath.split('/')
			filename = items[len(items)-1]
			if filename :
				filesplit = filename.split(os.extsep)
				soundName = filesplit[0]

				#if the soundName has something before the '.' add it to the playlist
				if soundName:

					if filesplit[1] == 'subplaylist':
						output += '\t(playlist\n'
						output += '\t\t(name "'+ filesplit[0] +'.S3DPlayListModel#0"))\n\n'
					else:
						output += '\t(sound\n'

						#check suffixes
						if '_SPA' in filename:
							output += '\t\t(spatialized true)\n'
						if '_UOS' in filename:
							output += '\t\t(unloadonstop true)\n'
						if '_PRE' in filename:
							output += '\t\t(preload true)\n'

                    				output += '\t\t(bundle\n'
		               			output += '\t\t\t(path "sounds/' + sys.argv[1] +'")\n'
                    				output += '\t\t\t(name "' + filesplit[0] +'")\n'
                    				output += '\t\t\t(extension "' + filesplit[1] +'")))\n'
output += ')\n'
print output
f = open('./../meta/S3DPlayListModel/'+sys.argv[2]+'.S3DPlayListModel#0.sexp','w+')
f.write(output)
f.close()
